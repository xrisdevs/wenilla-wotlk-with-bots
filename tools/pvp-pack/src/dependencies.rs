//! Auditable closure for static scenery and environmental audio. Dynamic hero/gear/pet
//! families remain roots; observed requests are supplementary, never the only roots.
use super::{Profile, norm, selected};
use anyhow::{Context, Result, ensure};
use benilla_formats::Chain;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet, VecDeque};

#[derive(Serialize)]
pub struct Plan {
    pub policy: &'static str,
    pub kept: BTreeMap<String, String>,
    pub absent_in_source: BTreeMap<String, String>,
    pub areas: BTreeSet<u32>,
    pub wmo_ids: BTreeSet<u32>,
    pub environmental_kits: BTreeSet<u32>,
    pub excluded_bytes: u64,
    pub kept_bytes: u64,
    pub excluded_files: usize,
}
struct Graph<'a> {
    chain: &'a Chain,
    names: BTreeSet<String>,
    siblings: BTreeMap<String, Vec<String>>,
    queue: VecDeque<String>,
    plan: Plan,
}
fn u32_at(b: &[u8], p: usize) -> Result<u32> {
    Ok(u32::from_le_bytes(
        b.get(p..p + 4)
            .context("truncated dependency record")?
            .try_into()?,
    ))
}
pub fn chunks(b: &[u8]) -> Result<Vec<([u8; 4], &[u8])>> {
    let mut out = Vec::new();
    let mut p = 0;
    while p < b.len() {
        ensure!(b.len() - p >= 8, "truncated chunk header");
        let size = u32_at(b, p + 4)? as usize;
        let end = p
            .checked_add(8)
            .and_then(|v| v.checked_add(size))
            .context("chunk overflow")?;
        let data = b.get(p + 8..end).context("truncated chunk body")?;
        out.push((b[p..p + 4].try_into()?, data));
        p = end;
    }
    Ok(out)
}
struct Dbc {
    data: Vec<u8>,
    count: usize,
    stride: usize,
    strings: usize,
}
impl Dbc {
    fn read(chain: &Chain, name: &str) -> Result<Self> {
        Self::parse(chain.read(&format!("DBFilesClient/{name}.dbc"))?)
    }
    fn parse(data: Vec<u8>) -> Result<Self> {
        ensure!(data.get(..4) == Some(b"WDBC"), "expected WDBC");
        let count = u32_at(&data, 4)? as usize;
        let stride = u32_at(&data, 12)? as usize;
        let bytes = u32_at(&data, 16)? as usize;
        ensure!(stride > 0, "invalid DBC stride");
        let strings = 20usize
            .checked_add(count.checked_mul(stride).context("DBC overflow")?)
            .context("DBC overflow")?;
        ensure!(
            strings.checked_add(bytes) == Some(data.len()),
            "truncated DBC"
        );
        Ok(Self {
            data,
            count,
            stride,
            strings,
        })
    }
    fn field(&self, row: usize, col: usize) -> Result<u32> {
        ensure!(
            row < self.count
                && col
                    .checked_mul(4)
                    .and_then(|p| p.checked_add(4))
                    .is_some_and(|end| end <= self.stride),
            "invalid DBC column"
        );
        u32_at(&self.data, 20 + row * self.stride + col * 4)
    }
    fn string(&self, row: usize, col: usize) -> Result<String> {
        let start = self
            .strings
            .checked_add(self.field(row, col)? as usize)
            .context("string overflow")?;
        let b = self.data.get(start..).context("invalid DBC string")?;
        let end = b
            .iter()
            .position(|v| *v == 0)
            .context("unterminated DBC string")?;
        Ok(std::str::from_utf8(&b[..end])?.to_string())
    }
}
fn canonical(s: &str) -> String {
    let mut s = norm(s.trim());
    while s.contains("//") {
        s = s.replace("//", "/");
    }
    if s.ends_with(".mdx") || s.ends_with(".mdl") {
        s.truncate(s.len() - 4);
        s.push_str(".m2");
    }
    s
}
// A file can contain binary arrays adjacent to its path strings. Scan printable runs,
// then identify rooted paths inside each run (also handles quoted Lua/XML strings).
fn references(bytes: &[u8]) -> BTreeSet<String> {
    let roots = [
        "world/",
        "dungeons/",
        "interiors/",
        "textures/",
        "tileset/",
        "interface/",
        "character/",
        "item/",
        "creature/",
        "spells/",
        "spell/",
        "particles/",
        "sound/",
        "environments/",
        "xtextures/",
        "cameras/",
    ];
    let extensions = [
        ".blp", ".m2", ".mdx", ".mdl", ".wmo", ".wav", ".mp3", ".ogg", ".lua", ".xml",
    ];
    let mut out = BTreeSet::new();
    for run in bytes.split(|b| !matches!(*b, 32..=126)) {
        if run.len() < 6 {
            continue;
        }
        let s = canonical(std::str::from_utf8(run).unwrap());
        for root in roots {
            for (start, _) in s.match_indices(root) {
                let tail = &s[start..];
                if let Some(end) = extensions
                    .iter()
                    .filter_map(|ext| tail.find(ext).map(|i| i + ext.len()))
                    .min()
                {
                    let candidate = &tail[..end];
                    if !candidate.contains(['"', '\'', '<', '>', '\n']) {
                        out.insert(canonical(candidate));
                    }
                }
            }
        }
    }
    out
}
fn dynamic_root(n: &str) -> bool {
    // Only these groups are candidates for dependency pruning. Unknown families stay
    // intact rather than silently falling out of a whitelist.
    !(n.starts_with("world/")
        || n.starts_with("dungeons/")
        || n.starts_with("interiors/")
        || n.starts_with("sound/music/")
        || n.starts_with("sound/ambience/"))
        || n.starts_with("world/environment/")
        || n.starts_with("sound/music/gluescreenmusic/")
}
impl Graph<'_> {
    fn add(&mut self, name: &str, why: &str) -> Result<()> {
        let name = canonical(name);
        if self.plan.kept.contains_key(&name) || self.plan.absent_in_source.contains_key(&name) {
            return Ok(());
        }
        if !self.names.contains(&name) {
            ensure!(
                self.chain.read(&name).is_err(),
                "referenced file absent from listfiles: {name}; complete the source inventory before pruning"
            );
            self.plan.absent_in_source.insert(name, why.into());
            return Ok(());
        }
        self.plan.kept.insert(name.clone(), why.into());
        self.queue.push_back(name);
        Ok(())
    }
    fn drain(&mut self) -> Result<()> {
        while let Some(name) = self.queue.pop_front() {
            let ext = name.rsplit('.').next().unwrap_or("");
            if !matches!(
                ext,
                "adt" | "wdt" | "wmo" | "m2" | "dbc" | "lua" | "xml" | "txt"
            ) {
                continue;
            }
            // SoundEntries is handled using joined kit paths and scoped environment ids.
            if name == "dbfilesclient/soundentries.dbc" {
                continue;
            }
            let bytes = self.chain.read(&name).with_context(|| name.clone())?;
            let source = if ext == "dbc" {
                let dbc = Dbc::parse(bytes.clone()).with_context(|| name.clone())?;
                bytes[dbc.strings..].to_vec()
            } else {
                bytes.clone()
            };
            for dep in references(&source) {
                self.add(&dep, &name)?;
            }
            if matches!(ext, "adt" | "wdt" | "wmo") {
                for (tag, data) in chunks(&bytes).with_context(|| name.clone())? {
                    if &tag == b"KNCM" {
                        self.plan.areas.insert(u32_at(data, 0x34)?);
                    }
                    if &tag == b"DHOM" {
                        self.plan.wmo_ids.insert(u32_at(data, 0x20)?);
                        let count = u32_at(data, 4)?;
                        ensure!(count < 10000, "invalid WMO group count");
                        for i in 0..count {
                            let group = format!("{}_{i:03}.wmo", name.trim_end_matches(".wmo"));
                            ensure!(
                                self.names.contains(&group),
                                "missing WMO group in source: {group}"
                            );
                            self.add(&group, &name)?;
                        }
                    }
                }
            }
            if ext == "m2" {
                if bytes.get(..4) == Some(b"MD20") {
                    let count = u32_at(&bytes, 0x100)? as usize;
                    let offset = u32_at(&bytes, 0x104)? as usize;
                    ensure!(
                        offset
                            .checked_add(count.checked_mul(0x24).context("event overflow")?)
                            .is_some_and(|end| end <= bytes.len()),
                        "truncated M2 events: {name}"
                    );
                    for i in 0..count {
                        let p = offset + i * 0x24;
                        if matches!(&bytes[p..p + 4], b"$SND" | b"$DSL" | b"$DSO") {
                            self.plan.environmental_kits.insert(u32_at(&bytes, p + 4)?);
                        }
                    }
                }
                let parent = name.rsplit_once('/').map(|x| x.0).unwrap_or("");
                let stem = name.trim_end_matches(".m2");
                // Keep every skin/animation sidecar and texture variant sharing the stem.
                // This also retains multiple LOD skins and non-default animation sub-ids.
                let siblings = self.siblings.get(parent).cloned().unwrap_or_default();
                for path in siblings {
                    if path.starts_with(stem)
                        && [".skin", ".anim", ".blp"].iter().any(|e| path.ends_with(e))
                    {
                        self.add(&path, &name)?;
                    }
                }
            }
        }
        Ok(())
    }
}
pub fn plan(
    chain: &Chain,
    profile: &Profile,
    maps: &BTreeSet<String>,
    listed: &[(String, u64)],
) -> Result<Plan> {
    let names: BTreeSet<_> = listed.iter().map(|(n, _)| norm(n)).collect();
    let mut siblings = BTreeMap::<String, Vec<String>>::new();
    for n in &names {
        if let Some((p, _)) = n.rsplit_once('/') {
            siblings.entry(p.into()).or_default().push(n.clone());
        }
    }
    let mut graph = Graph {
        chain,
        names,
        siblings,
        queue: VecDeque::new(),
        plan: Plan {
            policy: "pvp-dependency-closure-v2",
            kept: BTreeMap::new(),
            absent_in_source: BTreeMap::new(),
            areas: BTreeSet::new(),
            wmo_ids: BTreeSet::new(),
            environmental_kits: BTreeSet::new(),
            excluded_bytes: 0,
            kept_bytes: 0,
            excluded_files: 0,
        },
    };
    for (n, _) in listed {
        let n = norm(n);
        if selected(&n, maps, profile) && (n.starts_with("world/maps/") || dynamic_root(&n)) {
            graph.add(&n, "policy root: terrain or dynamic/shared family")?;
        }
    }
    // GroundEffectDoodad stores bare filenames; the runtime prepends this directory.
    let doodads = Dbc::read(chain, "GroundEffectDoodad")?;
    for r in 0..doodads.count {
        let file = doodads.string(r, 1)?;
        let file = file.rsplit(['\\', '/']).next().unwrap_or(&file);
        let stem = file.rsplit_once('.').map(|x| x.0).unwrap_or(file);
        if !stem.is_empty() {
            graph.add(
                &format!("World/NoDXT/Detail/{stem}.m2"),
                "GroundEffectDoodad dynamic path",
            )?;
        }
    }
    // Observed successes extend the roots, but never authorize removing unobserved files.
    for report in &profile.request_reports {
        let report: BTreeMap<String, u16> = serde_json::from_slice(&std::fs::read(report)?)?;
        for (n, status) in report {
            if (200..300).contains(&status) && n != "__index" {
                graph.add(&n, "observed successful request")?;
            }
        }
    }
    graph.drain()?;
    // All zone/subzone audio for supported PvP maps, plus sampled staging areas and
    // every retained building's alternate name sets (BG state can select any of them).
    let map_dbc = Dbc::read(chain, "Map")?;
    let mut map_ids = BTreeSet::new();
    for r in 0..map_dbc.count {
        if maps.contains(&norm(&map_dbc.string(r, 1)?)) {
            map_ids.insert(map_dbc.field(r, 0)?);
        }
    }
    let areas = Dbc::read(chain, "AreaTable")?;
    for r in 0..areas.count {
        if map_ids.contains(&areas.field(r, 1)?) {
            graph.plan.areas.insert(areas.field(r, 0)?);
        }
    }
    let mut music = BTreeSet::new();
    let mut intro = BTreeSet::new();
    let mut ambience = BTreeSet::new();
    let wmo = Dbc::read(chain, "WMOAreaTable")?;
    for r in 0..wmo.count {
        if graph.plan.wmo_ids.contains(&wmo.field(r, 1)?) {
            ambience.insert(wmo.field(r, 6)?);
            music.insert(wmo.field(r, 7)?);
            intro.insert(wmo.field(r, 8)?);
            graph.plan.areas.insert(wmo.field(r, 10)?);
        }
    }
    loop {
        let before = graph.plan.areas.len();
        for r in 0..areas.count {
            if graph.plan.areas.contains(&areas.field(r, 0)?) {
                graph.plan.areas.insert(areas.field(r, 2)?);
            }
        }
        if before == graph.plan.areas.len() {
            break;
        }
    }
    for r in 0..areas.count {
        if graph.plan.areas.contains(&areas.field(r, 0)?) {
            ambience.insert(areas.field(r, 7)?);
            music.insert(areas.field(r, 8)?);
            intro.insert(areas.field(r, 9)?);
        }
    }
    for (file, ids, cols) in [
        ("ZoneMusic", music, vec![6, 7]),
        ("ZoneIntroMusicTable", intro, vec![2]),
        ("SoundAmbience", ambience, vec![1, 2]),
    ] {
        let dbc = Dbc::read(chain, file)?;
        for r in 0..dbc.count {
            if ids.contains(&dbc.field(r, 0)?) {
                for c in &cols {
                    graph.plan.environmental_kits.insert(dbc.field(r, *c)?);
                }
            }
        }
    }
    // These tables can trigger environmental kits independently of the zone (spell
    // visuals, gameobjects, creatures, emitters and UI). Conservative numeric roots
    // retain extra files on id collisions rather than dropping a valid sound.
    for file in [
        "SoundEmitters",
        "CreatureSoundData",
        "GameObjectDisplayInfo",
        "SpellVisualKit",
        "EmotesTextSound",
        "NPCSounds",
        "VocalUISounds",
        "ChrRaces",
    ] {
        let key = format!("dbfilesclient/{}.dbc", file.to_ascii_lowercase());
        if !graph.names.contains(&key) {
            continue;
        }
        let table = Dbc::read(chain, file)?;
        for r in 0..table.count {
            for c in 0..table.stride / 4 {
                graph.plan.environmental_kits.insert(table.field(r, c)?);
            }
        }
    }
    let sounds = Dbc::read(chain, "SoundEntries")?;
    for r in 0..sounds.count {
        let id = sounds.field(r, 0)?;
        let kind = sounds.field(r, 1)?;
        let title = sounds.string(r, 2)?;
        if !matches!(kind, 28 | 50)
            || graph.plan.environmental_kits.contains(&id)
            || title.contains("DONOTRENAME")
        {
            let dir = sounds.string(r, 23)?;
            for col in 3..13 {
                let file = sounds.string(r, col)?;
                if file.is_empty() {
                    continue;
                }
                let path = if dir.is_empty() {
                    file
                } else {
                    format!("{}/{}", dir.trim_end_matches(['\\', '/']), file)
                };
                graph.add(&path, &format!("SoundEntries kit {id}: {title}"))?;
            }
        }
    }
    graph.drain()?;
    for (name, size) in listed {
        if graph.plan.kept.contains_key(&norm(name)) {
            graph.plan.kept_bytes += size;
        } else {
            graph.plan.excluded_files += 1;
            graph.plan.excluded_bytes += size;
        }
    }
    // Closure is invariant: every available static edge has already been enqueued.
    ensure!(graph.queue.is_empty(), "unfinished dependency traversal");
    Ok(graph.plan)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn closes_building_model_texture_and_animation_edges() -> Result<()> {
        let dir = std::env::temp_dir().join(format!(
            "wenilla-closure-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)?
                .as_nanos()
        ));
        std::fs::create_dir(&dir)?;
        let mut root = Vec::new();
        let mut header = vec![0; 64];
        header[4..8].copy_from_slice(&1u32.to_le_bytes());
        header[32..36].copy_from_slice(&77u32.to_le_bytes());
        for (tag, payload) in [
            (b"DHOM", header.as_slice()),
            (b"NDOM", b"World/Tree.mdx\0".as_slice()),
        ] {
            root.extend_from_slice(tag);
            root.extend_from_slice(&(payload.len() as u32).to_le_bytes());
            root.extend_from_slice(payload);
        }
        let mut model = vec![0; 0x12c];
        model[..4].copy_from_slice(b"MD20");
        model[0x100..0x104].copy_from_slice(&1u32.to_le_bytes());
        model[0x104..0x108].copy_from_slice(&0x108u32.to_le_bytes());
        model[0x108..0x10c].copy_from_slice(b"$SND");
        model[0x10c..0x110].copy_from_slice(&99u32.to_le_bytes());
        model.extend_from_slice(b"World/Tree.blp\0");
        let files = vec![
            ("world/root.wmo", root),
            ("world/root_000.wmo", vec![]),
            ("world/tree.m2", model),
            ("world/tree.blp", vec![1]),
            ("world/tree00.skin", vec![]),
            ("world/tree0001-02.anim", vec![]),
        ];
        let archive = dir.join("fixture.MPQ");
        let w = crate::Writer::new(&archive, files.len())?;
        for (name, data) in &files {
            w.add(&name.replace('/', "\\"), data)?;
        }
        w.finish()?;
        let chain = Chain::open(&archive)?;
        let names: BTreeSet<_> = files.iter().map(|(n, _)| n.to_string()).collect();
        let mut g = Graph {
            chain: &chain,
            names: names.clone(),
            siblings: BTreeMap::from([("world".into(), names.iter().cloned().collect())]),
            queue: VecDeque::new(),
            plan: Plan {
                policy: "test",
                kept: BTreeMap::new(),
                absent_in_source: BTreeMap::new(),
                areas: BTreeSet::new(),
                wmo_ids: BTreeSet::new(),
                environmental_kits: BTreeSet::new(),
                excluded_bytes: 0,
                kept_bytes: 0,
                excluded_files: 0,
            },
        };
        g.add("world/root.wmo", "test root")?;
        g.drain()?;
        assert_eq!(g.plan.kept.keys().cloned().collect::<BTreeSet<_>>(), names);
        assert!(g.plan.wmo_ids.contains(&77));
        assert!(g.plan.environmental_kits.contains(&99));
        assert!(g.plan.absent_in_source.is_empty());
        drop(g);
        drop(chain);
        std::fs::remove_dir_all(dir)?;
        Ok(())
    }
    #[test]
    fn extracts_binary_and_escaped_paths() {
        let refs=references(b"\xff\x04World\\\\Generic\\Tree.mdx\0<Texture file=\"World\\Tree.blp\"/>\0Sound\\Music\\A B.mp3\0");
        assert!(refs.contains("world/generic/tree.m2"));
        assert!(refs.contains("world/tree.blp"));
        assert!(refs.contains("sound/music/a b.mp3"));
    }
    #[test]
    fn malformed_records_fail_closed() {
        assert!(chunks(b"REVM\x05\0\0\0abc").is_err());
        assert!(Dbc::parse(b"WDBC".to_vec()).is_err());
    }
    #[test]
    fn dynamic_families_are_never_trace_only() {
        for n in [
            "character/human/a.blp",
            "item/a.blp",
            "creature/wolf/a.m2",
            "spells/fire.m2",
            "sound/spells/fire.wav",
            "tileset/foo.blp",
            "textures/minimap/a.blp",
        ] {
            assert!(dynamic_root(n));
        }
        for n in [
            "world/wmo/raid.wmo",
            "sound/music/raid.mp3",
            "sound/ambience/raid.wav",
        ] {
            assert!(!dynamic_root(n));
        }
    }
}
