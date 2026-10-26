//! Conservative PvP pack: retain shared assets, trim map terrain, preserve patch precedence.
use anyhow::{Context, Result, ensure};
use benilla_formats::Chain;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    ffi::{CString, c_void},
    fs,
    path::Path,
};

type Handle = *mut c_void;
unsafe extern "C" {
    fn SFileCreateArchive(name: *const i8, flags: u32, count: u32, out: *mut Handle) -> bool;
    fn SFileCloseArchive(archive: Handle) -> bool;
    fn SFileCreateFile(
        archive: Handle,
        name: *const i8,
        time: u64,
        size: u32,
        locale: u32,
        flags: u32,
        out: *mut Handle,
    ) -> bool;
    fn SFileWriteFile(file: Handle, data: *const c_void, size: u32, compression: u32) -> bool;
    fn SFileFinishFile(file: Handle) -> bool;
}
struct Writer(Handle);
impl Writer {
    fn new(path: &Path, count: usize) -> Result<Self> {
        let name = CString::new(path.to_str().context("non-UTF8 output path")?)?;
        let mut handle = std::ptr::null_mut();
        ensure!(
            unsafe {
                SFileCreateArchive(
                    name.as_ptr(),
                    0x01100000,
                    u32::try_from(count + 16)?,
                    &mut handle,
                )
            },
            "StormLib create failed"
        );
        Ok(Self(handle))
    }
    fn add(&self, name: &str, bytes: &[u8]) -> Result<()> {
        let name = CString::new(name)?;
        let size = u32::try_from(bytes.len())?;
        let mut file = std::ptr::null_mut();
        ensure!(
            unsafe { SFileCreateFile(self.0, name.as_ptr(), 0, size, 0, 0x200, &mut file) },
            "StormLib create file failed"
        );
        let wrote =
            bytes.is_empty() || unsafe { SFileWriteFile(file, bytes.as_ptr().cast(), size, 2) };
        let finished = unsafe { SFileFinishFile(file) };
        ensure!(wrote && finished, "StormLib write failed");
        Ok(())
    }
    fn finish(mut self) -> Result<()> {
        let handle = std::mem::replace(&mut self.0, std::ptr::null_mut());
        ensure!(
            unsafe { SFileCloseArchive(handle) },
            "StormLib close failed"
        );
        Ok(())
    }
}
impl Drop for Writer {
    fn drop(&mut self) {
        if !self.0.is_null() {
            unsafe {
                SFileCloseArchive(self.0);
            }
        }
    }
}
#[derive(Deserialize)]
struct Profile {
    staging: Vec<Staging>,
    #[serde(default)]
    extra_maps: Vec<String>,
}
#[derive(Deserialize)]
struct Staging {
    map: String,
    x: f64,
    y: f64,
    radius: i32,
}
#[derive(Serialize, Deserialize)]
struct Entry {
    name: String,
    size: u64,
    sha256: String,
}
#[derive(Serialize, Deserialize)]
struct Manifest {
    format: u32,
    policy: String,
    maps: Vec<String>,
    source_archive_bytes: u64,
    listed_files: usize,
    excluded_files: usize,
    unpacked_bytes: u64,
    archive_bytes: u64,
    files: Vec<Entry>,
}
fn norm(name: &str) -> String {
    name.replace('\\', "/").to_ascii_lowercase()
}
fn map_names(chain: &Chain) -> Result<BTreeSet<String>> {
    let data = chain.read("DBFilesClient\\Map.dbc")?;
    ensure!(data.len() >= 20 && &data[..4] == b"WDBC", "invalid Map.dbc");
    let u = |p| u32::from_le_bytes(data[p..p + 4].try_into().unwrap()) as usize;
    let (count, stride) = (u(4), u(12));
    ensure!(
        stride >= 12 && 20 + count * stride <= data.len(),
        "invalid DBC records"
    );
    let strings = 20 + count * stride;
    let mut maps = BTreeSet::new();
    for i in 0..count {
        let row = 20 + i * stride;
        if !matches!(u(row + 8), 3 | 4) {
            continue;
        }
        let start = strings + u(row + 4);
        let tail = data.get(start..).context("invalid DBC string offset")?;
        let end = tail
            .iter()
            .position(|b| *b == 0)
            .context("unterminated DBC string")?;
        maps.insert(String::from_utf8(tail[..end].to_vec())?.to_ascii_lowercase());
    }
    ensure!(!maps.is_empty(), "no PvP maps found");
    Ok(maps)
}
fn selected(name: &str, maps: &BTreeSet<String>, profile: &Profile) -> bool {
    let name = norm(name);
    if name.starts_with('(') {
        return false;
    }
    let Some(rest) = name.strip_prefix("world/maps/") else {
        // Keep shared data conservatively, including all item art, pets, sounds and UI.
        return !name.starts_with("movies/");
    };
    let Some((map, file)) = rest.split_once('/') else {
        return false;
    };
    if maps.contains(map) {
        return true;
    }
    for stage in &profile.staging {
        if !map.eq_ignore_ascii_case(&stage.map) {
            continue;
        }
        // Preserve map metadata and low-detail horizon; trim only high-detail terrain tiles.
        if !file.ends_with(".adt") {
            return true;
        }
        let stem = file.trim_end_matches(".adt");
        let parts: Vec<_> = stem.rsplitn(3, '_').collect();
        if parts.len() != 3 {
            return false;
        }
        let (Ok(y), Ok(x)) = (parts[0].parse::<i32>(), parts[1].parse::<i32>()) else {
            return false;
        };
        let center_x = (32.0 - stage.y / (1600.0 / 3.0)).floor() as i32;
        let center_y = (32.0 - stage.x / (1600.0 / 3.0)).floor() as i32;
        if (x - center_x).abs() <= stage.radius && (y - center_y).abs() <= stage.radius {
            return true;
        }
    }
    false
}
fn verify(archive: &Path, manifest: &Manifest) -> Result<()> {
    let packed = Chain::open(archive)?;
    // StormLib includes its generated internal listfile in that same listfile.
    // It is archive metadata, not a source game asset.
    let assets: BTreeSet<_> = packed
        .list()?
        .into_iter()
        .filter(|entry| !matches!(entry.name.as_str(), "(listfile)" | "(attributes)"))
        .map(|entry| norm(&entry.name))
        .collect();
    let expected: BTreeSet<_> = manifest
        .files
        .iter()
        .map(|entry| norm(&entry.name))
        .collect();
    ensure!(
        assets == expected,
        "archive asset names differ from manifest ({} vs {})",
        assets.len(),
        expected.len()
    );
    for (i, entry) in manifest.files.iter().enumerate() {
        let bytes = packed
            .read(&entry.name)
            .with_context(|| entry.name.clone())?;
        ensure!(
            bytes.len() as u64 == entry.size
                && format!("{:x}", Sha256::digest(&bytes)) == entry.sha256,
            "round-trip mismatch: {}",
            entry.name
        );
        if i % 10000 == 0 {
            eprintln!("Verified {i}/{}", manifest.files.len());
        }
    }
    Ok(())
}
fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    ensure!(
        args.len() >= 3,
        "usage: wenilla-pvp-pack inventory DATA | build DATA PROFILE OUTPUT_DIR | verify MPQ MANIFEST"
    );
    if args[1] == "verify" {
        let manifest: Manifest =
            serde_json::from_slice(&fs::read(args.get(3).context("manifest required")?)?)?;
        verify(Path::new(&args[2]), &manifest)?;
        println!("Verified every packed file");
        return Ok(());
    }
    let chain = Chain::open(Path::new(&args[2]))?;
    let entries = chain.list()?;
    ensure!(!entries.is_empty(), "archives have no readable listfiles");
    if args[1] == "inventory" {
        let mut groups = BTreeMap::<String, (u64, u64)>::new();
        for entry in entries {
            let name = norm(&entry.name);
            let parts: Vec<_> = name.split('/').collect();
            let n = if name.starts_with("world/") {
                3
            } else if name.starts_with("sound/") {
                2
            } else {
                1
            };
            let row = groups
                .entry(parts[..parts.len().min(n)].join("/"))
                .or_default();
            row.0 += 1;
            row.1 += entry.size;
        }
        println!("{}", serde_json::to_string_pretty(&groups)?);
        return Ok(());
    }
    ensure!(
        args[1] == "build" && args.len() == 5,
        "build DATA PROFILE OUTPUT_DIR"
    );
    let profile: Profile = serde_json::from_slice(&fs::read(&args[3])?)?;
    ensure!(
        profile
            .staging
            .iter()
            .all(|s| s.x.is_finite() && s.y.is_finite() && (0..=8).contains(&s.radius)),
        "invalid staging bounds"
    );
    let mut maps = map_names(&chain)?;
    maps.extend(profile.extra_maps.iter().map(|s| s.to_ascii_lowercase()));
    let output = Path::new(&args[4]);
    // Never overwrite a pack or write into the source install.
    ensure!(!output.exists(), "output exists; choose a new directory");
    let absolute_output = std::path::absolute(output)?;
    let existing_parent = absolute_output
        .ancestors()
        .find(|p| p.exists())
        .context("output has no existing parent")?
        .canonicalize()?;
    let source = fs::canonicalize(&args[2])?;
    let source_directory = if source.is_dir() {
        source.as_path()
    } else {
        source.parent().context("source has no parent")?
    };
    ensure!(
        !existing_parent.starts_with(source_directory),
        "output must be outside the original asset directory"
    );
    fs::create_dir_all(output)?;
    let mut manifest = Manifest {
        format: 1,
        policy: "conservative-shared-assets-v1".into(),
        maps: maps.iter().cloned().collect(),
        source_archive_bytes: 0,
        listed_files: entries.len(),
        excluded_files: 0,
        unpacked_bytes: 0,
        archive_bytes: 0,
        files: vec![],
    };
    for archive in chain.archive_paths() {
        manifest.source_archive_bytes += fs::metadata(archive)?.len();
    }
    let mut kept: Vec<_> = entries
        .into_iter()
        .filter(|e| selected(&e.name, &maps, &profile))
        .collect();
    kept.sort_by_key(|e| norm(&e.name));
    manifest.excluded_files = manifest.listed_files - kept.len();
    // Check every selected map is really represented before spending time packing.
    for map in &maps {
        ensure!(
            kept.iter()
                .any(|e| norm(&e.name) == format!("world/maps/{map}/{map}.wdt")),
            "missing map WDT: {map}"
        );
    }
    let temporary = output.join("pvp.MPQ.partial");
    let writer = Writer::new(&temporary, kept.len())?;
    for (i, entry) in kept.iter().enumerate() {
        let bytes = chain
            .read(&entry.name)
            .with_context(|| entry.name.clone())?;
        writer
            .add(&entry.name, &bytes)
            .with_context(|| entry.name.clone())?;
        manifest.unpacked_bytes += bytes.len() as u64;
        manifest.files.push(Entry {
            name: entry.name.clone(),
            size: bytes.len() as u64,
            sha256: format!("{:x}", Sha256::digest(&bytes)),
        });
        if i % 5000 == 0 {
            eprintln!(
                "Packed {i}/{} ({:.2} GiB input)",
                kept.len(),
                manifest.unpacked_bytes as f64 / 1073741824.0
            );
        }
    }
    writer.finish()?;
    manifest.archive_bytes = fs::metadata(&temporary)?.len();
    fs::write(
        output.join("manifest.json"),
        serde_json::to_vec_pretty(&manifest)?,
    )?;
    fs::copy(&args[3], output.join("profile.json"))?;
    eprintln!("Verifying every byte using the client's own MPQ reader...");
    verify(&temporary, &manifest)?;
    fs::rename(temporary, output.join("pvp.MPQ"))?;
    println!(
        "{} files; {:.2} GiB -> {:.2} GiB ({:.1}% smaller). All packed files verified.",
        manifest.files.len(),
        manifest.source_archive_bytes as f64 / 1073741824.0,
        manifest.archive_bytes as f64 / 1073741824.0,
        100.0 * (1.0 - manifest.archive_bytes as f64 / manifest.source_archive_bytes as f64)
    );
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn selects_only_pvp_and_staging_terrain() {
        let profile = Profile {
            staging: vec![Staging {
                map: "Azeroth".into(),
                x: -8949.95,
                y: -132.493,
                radius: 2,
            }],
            extra_maps: vec![],
        };
        let maps = BTreeSet::from(["pvpzone05".into()]);
        assert!(selected(
            "World\\Maps\\PVPZone05\\PVPZone05_32_32.adt",
            &maps,
            &profile
        ));
        assert!(selected(
            "World/Maps/Azeroth/Azeroth_32_48.adt",
            &maps,
            &profile
        ));
        assert!(!selected(
            "World/Maps/Azeroth/Azeroth_0_0.adt",
            &maps,
            &profile
        ));
        assert!(!selected(
            "World/Maps/Northrend/Northrend.wdt",
            &maps,
            &profile
        ));
        assert!(selected(
            "Item/ObjectComponents/Weapon/Sword.m2",
            &maps,
            &profile
        ));
        assert!(selected("Sound/Spells/Fire.wav", &maps, &profile));
    }
    #[test]
    fn storm_archive_roundtrip_and_patch_override() -> Result<()> {
        let dir = std::env::temp_dir().join(format!("wenilla-mpq-test-{}", std::process::id()));
        fs::create_dir_all(dir.join("enUS"))?;
        for name in [
            "common.MPQ",
            "enUS/locale-enUS.MPQ",
            "enUS/speech-enUS.MPQ",
            "patch.MPQ",
        ] {
            let w = Writer::new(&dir.join(name), 4)?;
            w.add(
                "Interface\\Test.txt",
                if name == "patch.MPQ" {
                    b"patched"
                } else {
                    b"base"
                },
            )?;
            w.add("Empty", b"")?;
            w.finish()?;
        }
        let chain = Chain::open(&dir)?;
        assert_eq!(chain.read("interface/test.txt")?, b"patched");
        let w = Writer::new(&dir.join("pvp.MPQ"), 4)?;
        let large: Vec<u8> = (0..200_000).map(|i| (i % 251) as u8).collect();
        w.add("Interface\\Test.txt", &chain.read("Interface\\Test.txt")?)?;
        w.add("Empty", b"")?;
        w.add("Large", &large)?;
        w.finish()?;
        let packed = Chain::open(&dir.join("pvp.MPQ"))?;
        assert_eq!(packed.read("interface/test.txt")?, b"patched");
        assert!(packed.read("Empty")?.is_empty());
        assert_eq!(packed.read("Large")?, large);
        fs::remove_dir_all(dir)?;
        Ok(())
    }
}
