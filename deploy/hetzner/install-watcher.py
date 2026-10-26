#!/usr/bin/env python3
"""Install a per-user macOS launchd timer; deployment configuration stays private."""
import argparse, json, os, pathlib, plistlib, subprocess, sys
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config',type=pathlib.Path,required=True)
parser.add_argument('--interval',type=int,default=60)
args=parser.parse_args()
if sys.platform!='darwin':raise SystemExit('On Linux, run pipeline.py from a user systemd timer or cron instead.')
config=args.config.resolve();settings=json.loads(config.read_text())
home=pathlib.Path(settings['state_directory']);home.mkdir(parents=True,exist_ok=True)
label='dev.wenilla.hetzner-deploy'
plist=pathlib.Path.home()/'Library/LaunchAgents'/f'{label}.plist';plist.parent.mkdir(exist_ok=True)
runner=pathlib.Path(__file__).with_name('pipeline.py').resolve()
value={'Label':label,'ProgramArguments':[sys.executable,str(runner),'--config',str(config)],
       'StartInterval':args.interval,'RunAtLoad':True,'ProcessType':'Background',
       'WorkingDirectory':str(runner.parents[2]),
       'EnvironmentVariables':{'PATH':os.environ['PATH'],'HOME':str(pathlib.Path.home())},
       'StandardOutPath':str(home/'pipeline.log'),'StandardErrorPath':str(home/'pipeline.log')}
plist.write_bytes(plistlib.dumps(value));plist.chmod(0o600)
domain=f'gui/{os.getuid()}'
subprocess.run(['launchctl','bootout',domain+'/'+label],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
subprocess.run(['launchctl','bootstrap',domain,str(plist)],check=True)
print('Installed local watcher:',label)
print('Log:',home/'pipeline.log')
