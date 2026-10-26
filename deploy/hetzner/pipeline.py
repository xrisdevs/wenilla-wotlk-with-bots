#!/usr/bin/env python3
"""One local-only deployment poll. Schedule with launchd/cron; never run in GitHub Actions."""
import argparse, fcntl, gzip, json, os, pathlib, shlex, shutil, subprocess, sys, time, urllib.request


def run(args, cwd=None, **kwargs):
    return subprocess.run(args, cwd=cwd, check=True, **kwargs)


def output(args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=pathlib.Path, required=True)
    parser.add_argument('--retry', action='store_true', help='Retry a previously failed commit')
    parser.add_argument('--check', action='store_true', help='Report pending revision without deploying')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    home = pathlib.Path(config['state_directory']).resolve(); home.mkdir(parents=True, exist_ok=True)
    with (home/'pipeline.lock').open('w') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        state_path = home/'state.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        sha = output(['git','ls-remote',config['repository'],'refs/heads/arena-with-bots']).split()[0]
        if args.check:
            print(json.dumps({'remote':sha, 'deployed':state.get('deployed'), 'failed':state.get('failed')})); return
        if sha == state.get('deployed') or (sha == state.get('failed') and not args.retry): return
        if not state.get('deployed'): raise SystemExit('Initialize state.json with the verified first deployment before enabling automatic releases.')
        def save():
            temp=state_path.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2)+'\n');temp.chmod(0o600);temp.replace(state_path)
        try:
            print(time.strftime('%Y-%m-%d %H:%M:%S'), 'Deploying',sha,flush=True)
            run(['docker','info'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            mirror=home/'mirror.git'
            if not mirror.exists(): run(['git','clone','--mirror',config['repository'],str(mirror)])
            else: run(['git','--git-dir',str(mirror),'fetch','origin'])
            release=home/'releases'/sha
            if not release.exists():
                release.parent.mkdir(exist_ok=True)
                run(['git','clone','--shared',str(mirror),str(release)])
            run(['git','checkout','--detach',sha],cwd=release)
            def changed(paths):
                return bool(output(['git','diff','--name-only',state['deployed'],sha,'--',*paths],cwd=release))
            core=changed(['sources.json','patches/server.patch','custom','docker/Dockerfile','docker/scripts/build.sh'])
            browser=changed(['sources.json','patches/benilla-browser.patch','client','addons','controller','runtime/arena-host','docker/browser.Dockerfile','docker/scripts/browser.sh'])
            sql=changed(['custom/sql','scripts/init-arena.py'])
            (release/'.env').write_text('WOW_CLIENT_DIR=/unused\nMYSQL_ROOT_PASSWORD=build-only\nMYSQL_PASSWORD=build-only\nARENA_SOAP_PASS=build-only\n')
            (release/'.env').chmod(0o600)
            run([sys.executable,'scripts/audit-public.py'],cwd=release)
            run([sys.executable,'-m','unittest','discover','-s','tests'],cwd=release)
            venv=home/'test-venv'
            if not venv.exists(): run([sys.executable,'-m','venv',str(venv)])
            python=str(venv/'bin/python')
            run([python,'-m','pip','install','-q','-r','controller/lobby/requirements.txt'],cwd=release)
            run([python,'-m','unittest','discover','-s','controller/lobby','-p','test_*.py'],cwd=release)
            run([python,'-m','unittest','discover','-s','controller','-p','test_*.py'],cwd=release)
            compose=['docker','compose','-p','wenilla-release']
            run(compose+['config','--quiet'],cwd=release)
            if core:
                run([sys.executable,'scripts/setup-sources.py','server'],cwd=release)
                run(['bash','scripts/apply-custom.sh'],cwd=release)
                run(compose+['--profile','build','build','build'],cwd=release)
                run(compose+['--profile','build','run','--rm','-e','JOBS=2','build'],cwd=release)
            if browser:
                run(['npm','ci','--ignore-scripts'],cwd=release)
                run(['npm','run','test:recovery'],cwd=release)
                # WebAssembly packaging can exceed an 8 GB Docker VM while games are running.
                # Extra swap belongs to the Docker Linux VM, not the host's system settings.
                low_memory=int(output(['docker','info','--format','{{.MemTotal}}'])) < 12*1024**3
                if low_memory:
                    if shutil.disk_usage(home).free < 12*1024**3: raise RuntimeError('Need 12 GB free disk for a low-memory browser build')
                    run(['docker','run','--rm','--privileged','-v','wenilla-pipeline-swap:/swap','ubuntu:24.04','sh','-c',
                         'if ! swapon --show --noheadings --output NAME | grep -q build.swap; then fallocate -l 8G /swap/build.swap && chmod 600 /swap/build.swap && mkswap /swap/build.swap && swapon /swap/build.swap; fi'])
                try:
                    run(compose+['--profile','browser','build','browser'],cwd=release)
                finally:
                    if low_memory:
                        cleanup=subprocess.run(['docker','run','--rm','--privileged','-v','wenilla-pipeline-swap:/swap','ubuntu:24.04','sh','-c','swapoff /swap/build.swap && rm /swap/build.swap'])
                        if cleanup.returncode == 0: run(['docker','volume','rm','wenilla-pipeline-swap'])
            current=output(['git','ls-remote',config['repository'],'refs/heads/arena-with-bots']).split()[0]
            if current != sha:
                print('Newer commit arrived during build; skipping superseded release.',flush=True);return
            ssh=['ssh','-F',config['ssh_config'],config.get('ssh_host','wenilla-hetzner')]
            remote=config.get('remote_directory','/opt/wenilla')
            images=[]
            if core: images.append('wenilla/trinitycore')
            if browser: images.append('wenilla-release-browser')
            if images:
                producer=subprocess.Popen(['docker','save',*images],stdout=subprocess.PIPE)
                zipper=subprocess.Popen(['gzip','-1'],stdin=producer.stdout,stdout=subprocess.PIPE);producer.stdout.close()
                receiver=run(ssh+['gunzip | docker load'],stdin=zipper.stdout);zipper.stdout.close()
                if zipper.wait() or producer.wait(): raise RuntimeError('Docker image transfer failed')
            if browser: run(ssh+['docker tag wenilla-release-browser wenilla-wotlk-browser:latest'])
            if core:
                destination=remote+'/artifacts/deploy/'+sha
                run(ssh+['mkdir -p '+shlex.quote(destination)+' && chmod 700 '+shlex.quote(destination)])
                producer=subprocess.Popen(['docker','run','--rm','-v','wenilla-release_tc-install:/from:ro','wenilla/trinitycore','tar','-C','/from','-czf','-','.'],stdout=subprocess.PIPE)
                run(ssh+['cat > '+shlex.quote(destination+'/install.tar.gz')],stdin=producer.stdout);producer.stdout.close()
                if producer.wait(): raise RuntimeError('Server install transfer failed')
            # Send the reviewed activation script over stdin; the running checkout may predate it.
            command='python3 - '+shlex.join([remote,sha,str(int(core)),str(int(sql))])
            with (release/'deploy/hetzner/activate.py').open('rb') as script: run(ssh+[command],stdin=script)
            with urllib.request.urlopen(config['url'].rstrip('/')+'/healthz',timeout=30) as response:
                if not json.load(response).get('ready'): raise RuntimeError('Public health check failed')
            state.update(deployed=sha,failed=None,completed=time.time());save()
            print('Deployed',sha,'to',config['url'],flush=True)
        except Exception as exc:
            state.update(failed=sha,error=str(exc),failed_at=time.time());save()
            raise

if __name__ == '__main__': main()
