pub mod backend;

use axum::{
    Json, Router,
    extract::{ConnectInfo, DefaultBodyLimit, Request, State},
    http::{HeaderMap, HeaderValue, StatusCode, Uri},
    middleware::{self, Next},
    response::{IntoResponse, Redirect, Response},
    routing::{get, post},
};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use rand::{Rng, RngCore, rngs::OsRng};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use sqlx::{MySqlPool, Row, SqlitePool};
use std::{
    collections::{HashMap, VecDeque},
    net::SocketAddr,
    path::Path,
    sync::Arc,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::sync::Mutex;

const COOKIE: &str = "arena_guest";
const LOADOUT_VERSION: i64 = 2;
fn now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}
fn idle() -> Value {
    json!({"state":"idle"})
}

#[derive(Debug)]
pub struct Error(StatusCode, String);
type Result<T> = std::result::Result<T, Error>;
fn error(status: StatusCode, message: &str) -> Error {
    Error(status, message.into())
}
fn invalid(message: &str) -> Error {
    error(StatusCode::BAD_REQUEST, message)
}
fn conflict(message: &str) -> Error {
    error(StatusCode::CONFLICT, message)
}
impl From<sqlx::Error> for Error {
    fn from(_: sqlx::Error) -> Self {
        error(
            StatusCode::SERVICE_UNAVAILABLE,
            "The character database is unavailable",
        )
    }
}
impl IntoResponse for Error {
    fn into_response(self) -> Response {
        (self.0, Json(json!({"error":self.1}))).into_response()
    }
}
#[derive(Clone)]
struct Guest {
    account: i64,
    username: String,
    password: String,
}
#[derive(Clone)]
struct Character {
    name: String,
    build: i64,
    prepared: i64,
}
impl Character {
    fn json(&self) -> Value {
        json!({"name":self.name,"build":self.build,"prepared":self.prepared})
    }
}
#[derive(Clone)]
struct Entry {
    account: i64,
    name: String,
    size: usize,
    seen: f64,
    joined: f64,
    healer: bool,
}
#[derive(Default)]
struct Live {
    queues: HashMap<usize, Vec<Entry>>,
    games: HashMap<i64, Value>,
    teams: HashMap<String, Vec<Entry>>,
    used_codes: HashMap<String, f64>,
    limits: HashMap<String, VecDeque<f64>>,
    last_start: HashMap<i64, f64>,
}
impl Live {
    fn prune_teams(&mut self) {
        for team in self.teams.values_mut() {
            team.retain(|e| now() - e.seen <= 20.0);
        }
        self.teams.retain(|_, team| !team.is_empty());
        self.used_codes.retain(|_, used| now() - *used < 300.0);
    }
    fn join_team(&mut self, code: &str, entry: Entry) -> Result<()> {
        self.prune_teams();
        if self.used_codes.contains_key(code) {
            return Err(conflict("Team code already used. Create a new code."));
        }
        if self
            .teams
            .get(code)
            .is_some_and(|team| team[0].size != entry.size)
        {
            return Err(conflict("Choose the same match format as your teammate."));
        }
        self.cancel(entry.account);
        self.teams.entry(code.into()).or_default().push(entry);
        Ok(())
    }
    fn cancel(&mut self, account: i64) {
        for team in self.teams.values_mut() {
            team.retain(|e| e.account != account);
        }
        self.teams.retain(|_, team| !team.is_empty());
        for q in self.queues.values_mut() {
            q.retain(|e| e.account != account);
        }
    }
    fn status(&self, account: i64) -> Value {
        for (code, team) in &self.teams {
            if let Some(e) = team.iter().find(|e| e.account == account) {
                return json!({"state":"queued","mode":"coop","code":code,"size":e.size,"waiting":team.len(),"needed":2});
            }
        }
        for (size, q) in &self.queues {
            if let Some(e) = q.iter().find(|e| e.account == account) {
                return json!({"state":"queued","size":size,"waiting":q.len(),"needed":size*2,"seconds":(now()-e.joined) as u64});
            }
        }
        self.games.get(&account).cloned().unwrap_or_else(idle)
    }
}
pub struct App {
    db: SqlitePool,
    mysql: MySqlPool,
    soap: backend::Soap,
    builds: Value,
    live: Mutex<Live>,
    origin: String,
    login_host: String,
    world_host: String,
}
impl App {
    pub async fn open(home: &Path, builds: &Path) -> anyhow::Result<Arc<Self>> {
        std::fs::create_dir_all(home)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(home, std::fs::Permissions::from_mode(0o700))?;
        }
        let db = open_state(&home.join("guests.sqlite")).await?;
        let origin = std::env::var("ARENA_PUBLIC_ORIGIN")?
            .trim_end_matches('/')
            .to_string();
        let parsed = reqwest::Url::parse(&origin)?;
        anyhow::ensure!(
            matches!(parsed.scheme(), "http" | "https")
                && parsed.host_str().is_some()
                && parsed.path() == "/"
                && parsed.query().is_none()
                && parsed.fragment().is_none()
                && parsed.username().is_empty()
                && parsed.password().is_none(),
            "ARENA_PUBLIC_ORIGIN must be an HTTP(S) origin"
        );
        let builds: Value = serde_json::from_slice(&std::fs::read(builds)?)?;
        anyhow::ensure!(
            builds.as_array().is_some_and(|b| !b.is_empty()),
            "Missing build catalogue"
        );
        Ok(Arc::new(Self {
            db,
            mysql: backend::database().await?,
            soap: backend::Soap::new()?,
            builds,
            live: Mutex::new(Live::default()),
            origin,
            login_host: backend::env("ARENA_LOGIN_HOST", "127.0.0.1"),
            world_host: backend::env("ARENA_WORLD_HOST", "127.0.0.1"),
        }))
    }
    fn build(&self, id: i64) -> Result<&Value> {
        self.builds
            .as_array()
            .unwrap()
            .iter()
            .find(|b| b["id"].as_i64() == Some(id))
            .ok_or_else(|| invalid("Unknown build"))
    }
    async fn guest(&self, headers: &HeaderMap) -> Result<Guest> {
        let token = cookie(headers).unwrap_or_default();
        let row = sqlx::query("SELECT account,username,password FROM guests WHERE token=?")
            .bind(hex::encode(Sha256::digest(token.as_bytes())))
            .fetch_optional(&self.db)
            .await?
            .ok_or_else(|| {
                error(
                    StatusCode::UNAUTHORIZED,
                    "Guest session expired. Reload the lobby.",
                )
            })?;
        Ok(Guest {
            account: row.get(0),
            username: row.get(1),
            password: row.get(2),
        })
    }
    async fn owned(&self, g: &Guest, d: &Value, prepared: bool) -> Result<Character> {
        let name = d["name"]
            .as_str()
            .filter(|s| valid_name(s))
            .ok_or_else(|| invalid("Use 2–12 letters for your character name."))?;
        let row = sqlx::query(
            "SELECT name,build,prepared FROM characters WHERE account=? AND name=? COLLATE NOCASE",
        )
        .bind(g.account)
        .bind(name)
        .fetch_optional(&self.db)
        .await?
        .ok_or_else(|| {
            error(
                StatusCode::FORBIDDEN,
                "Choose and prepare your own character first.",
            )
        })?;
        let c = Character {
            name: row.get(0),
            build: row.get(1),
            prepared: row.get(2),
        };
        if prepared && c.prepared != LOADOUT_VERSION {
            return Err(error(
                StatusCode::FORBIDDEN,
                "Choose and prepare your own character first.",
            ));
        }
        Ok(c)
    }
    async fn online(&self, g: &Guest, c: &Character) -> Result<i64> {
        let row = sqlx::query(
            "SELECT class,online FROM characters.characters WHERE account=? AND name=?",
        )
        .bind(g.account)
        .bind(&c.name)
        .fetch_optional(&self.mysql)
        .await?;
        match row {
            Some(r) if r.get::<u8, _>("online") == 1 => Ok(r.get::<u8, _>("class") as i64),
            _ => Err(conflict("Character is still connecting.")),
        }
    }
    async fn public(&self, g: &Guest) -> Result<Value> {
        let rows = sqlx::query("SELECT name,build,prepared FROM characters WHERE account=?")
            .bind(g.account)
            .fetch_all(&self.db)
            .await?;
        let chars: Vec<_> = rows.iter().map(|r| json!({"name":r.get::<String,_>(0),"build":r.get::<i64,_>(1),"prepared":r.get::<i64,_>(2)})).collect();
        Ok(json!({"account":g.username,"characters":chars,"builds":self.builds}))
    }
    async fn command(&self, cmd: &str) -> Result<String> {
        self.soap.command(cmd).await.map_err(|_| {
            error(
                StatusCode::SERVICE_UNAVAILABLE,
                "World server is unavailable",
            )
        })
    }
    async fn match_team(&self, live: &mut Live, code: &str) {
        live.prune_teams();
        let Some(team) = live.teams.get(code).filter(|t| t.len() == 2).cloned() else {
            return;
        };
        let size = team[0].size;
        // Consume before sending: a transport timeout must never start the team twice.
        live.teams.remove(code);
        live.used_codes.insert(code.into(), now());
        let result = self
            .command(&format!(
                "botarena lobby match {size} bots {} {}",
                team[0].name, team[1].name
            ))
            .await;
        let id = result.as_ref().ok().and_then(|s| match_id(s));
        for e in team {
            live.games.insert(e.account, match id {
                Some(id) => json!({"state":"playing","mode":"coop","size":size,"match":id}),
                None => json!({"state":"error","message":"Could not start the team match. Return to the lobby and create a new code."}),
            });
        }
    }
    async fn matchmake(&self, live: &mut Live, size: usize) -> Result<()> {
        let q = live.queues.entry(size).or_default();
        q.retain(|e| now() - e.seen <= 20.0);
        if q.len() < size * 2 {
            return Ok(());
        }
        let selected = q[..size * 2].to_vec();
        let names = team_names(&selected);
        let result = self
            .command(&format!("botarena lobby match {size} players {names}"))
            .await;
        // Consume the attempted group even on a transport error: never repeat an uncertain start.
        let id = result.as_ref().ok().and_then(|s| match_id(s));
        for e in selected {
            live.cancel(e.account);
            live.games.insert(e.account, match id {
                Some(id) => json!({"state":"playing","mode":"players","size":size,"match":id}),
                None => json!({"state":"error","message":"A queued player became unavailable. Join the queue again."}),
            });
        }
        Ok(())
    }
}
pub async fn open_state(path: &Path) -> anyhow::Result<SqlitePool> {
    // SQLx workers keep SQLite work off the async networking threads. One connection also
    // preserves the old service's serialized writes and existing schema without a migration.
    let options = sqlx::sqlite::SqliteConnectOptions::new()
        .filename(path)
        .create_if_missing(true)
        .busy_timeout(Duration::from_secs(5));
    let db = sqlx::sqlite::SqlitePoolOptions::new()
        .max_connections(1)
        .connect_with(options)
        .await?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?;
    }
    sqlx::raw_sql("CREATE TABLE IF NOT EXISTS guests(token TEXT PRIMARY KEY, account INTEGER UNIQUE, username TEXT, password TEXT, created REAL); CREATE TABLE IF NOT EXISTS characters(account INTEGER, name TEXT UNIQUE COLLATE NOCASE, build INTEGER, prepared INTEGER DEFAULT 0, PRIMARY KEY(account,name));").execute(&db).await?;
    Ok(db)
}
fn cookie(headers: &HeaderMap) -> Option<&str> {
    headers
        .get_all("cookie")
        .iter()
        .filter_map(|h| h.to_str().ok())
        .flat_map(|s| s.split(';'))
        .filter_map(|s| s.trim().split_once('='))
        .find(|(k, _)| *k == COOKIE)
        .map(|(_, v)| v)
}
pub fn valid_name(s: &str) -> bool {
    (2..=12).contains(&s.len()) && s.bytes().all(|b| b.is_ascii_alphabetic())
}
fn random_name() -> String {
    let mut rng = OsRng;
    let prefixes = ["Ash", "Val", "Thal", "Nor", "Zen", "Kae", "Rav"];
    let mut s = prefixes[rng.gen_range(0..prefixes.len())].to_string();
    for i in 0..6 {
        let letters = if i % 2 == 0 { b"aeiou" } else { b"rstnl" };
        s.push(letters[rng.gen_range(0..5)] as char);
    }
    s
}
fn match_id(s: &str) -> Option<u64> {
    s.split_once("LOBBY_OK match ")?
        .1
        .split_whitespace()
        .next()?
        .parse()
        .ok()
}
fn team_names(selected: &[Entry]) -> String {
    let mut teams = [Vec::new(), Vec::new()];
    for e in selected
        .iter()
        .filter(|e| e.healer)
        .chain(selected.iter().filter(|e| !e.healer))
    {
        let side = usize::from(teams[0].len() > teams[1].len());
        teams[side].push(e.name.as_str());
    }
    teams.into_iter().flatten().collect::<Vec<_>>().join(" ")
}
fn foreign(headers: &HeaderMap, origin: &str) -> bool {
    headers
        .get("origin")
        .is_some_and(|v| v.to_str().ok() != Some(origin))
        || headers
            .get("sec-fetch-site")
            .is_some_and(|v| v == "cross-site")
}
async fn api_boundary(State(app): State<Arc<App>>, req: Request, next: Next) -> Response {
    let mut response = if foreign(req.headers(), &app.origin) {
        error(StatusCode::FORBIDDEN, "Cross-origin request refused").into_response()
    } else {
        next.run(req).await
    };
    response
        .headers_mut()
        .insert("cache-control", HeaderValue::from_static("no-store"));
    response.headers_mut().insert(
        "x-content-type-options",
        HeaderValue::from_static("nosniff"),
    );
    response
}
async fn game_boundary(State(app): State<Arc<App>>, req: Request, next: Next) -> Response {
    if foreign(req.headers(), &app.origin) {
        return error(
            StatusCode::FORBIDDEN,
            "Cross-origin game connection refused",
        )
        .into_response();
    }
    match app.guest(req.headers()).await {
        Ok(_) => next.run(req).await,
        Err(e) => e.into_response(),
    }
}
pub fn router(
    app: Arc<App>,
    chain: Arc<benilla_formats::Chain>,
    www: &Path,
    lobby: &Path,
) -> Router {
    let api = Router::new()
        .route("/session", post(session))
        .route("/credentials", get(credentials))
        .route("/characters", post(reserve))
        .route("/prepare", post(prepare))
        .route("/play", post(play))
        .route("/queue", get(queue).delete(cancel_queue))
        .route("/leave", post(leave))
        .route("/recover", post(recover))
        .layer(DefaultBodyLimit::max(16384))
        .with_state(app.clone())
        .layer(middleware::from_fn_with_state(app.clone(), api_boundary));
    let protected = wenilla_host::data::router(chain)
        .merge(wenilla_host::ws::router_map([
            (3724, Arc::<str>::from(app.login_host.clone())),
            (8085, Arc::<str>::from(app.world_host.clone())),
        ]))
        .route_layer(middleware::from_fn_with_state(app.clone(), game_boundary));
    Router::new()
        .nest("/api", api)
        .route("/healthz", get(health).with_state(app))
        .route_service(
            "/",
            tower_http::services::ServeFile::new(lobby.join("index.html")),
        )
        .nest_service("/lobby", tower_http::services::ServeDir::new(lobby))
        .merge(gateway_router(protected, www))
}
// The client loads addons through absolute /addons URLs as well as /game/*.
// Preserve the original gateway's root static fallback, while named asset/socket
// routes take priority and retain their guest boundary.
fn gateway_router(protected: Router, www: &Path) -> Router {
    Router::new()
        .nest("/game/", game_router(protected.clone(), www))
        .merge(protected)
        .merge(wenilla_host::static_site::router(www))
}
// Axum's nested fallback does not match the empty trailing-slash tail. Give
// the iframe entry an explicit route, preserving launch/recovery query options.
fn game_router(protected: Router, www: &Path) -> Router {
    protected
        .merge(wenilla_host::static_site::router(www))
        .route(
            "/",
            get(|uri: Uri| async move {
                let query = uri.query().map(|q| format!("?{q}")).unwrap_or_default();
                Redirect::temporary(&format!("/game/index.html{query}"))
            }),
        )
}

async fn session(
    State(app): State<Arc<App>>,
    headers: HeaderMap,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
) -> Result<Response> {
    match app.guest(&headers).await {
        Ok(g) => return Ok(Json(app.public(&g).await?).into_response()),
        Err(Error(StatusCode::UNAUTHORIZED, _)) => {}
        Err(e) => return Err(e),
    }
    let mut live = app.live.lock().await;
    let ip = if std::env::var_os("FLY_APP_NAME").is_some() {
        headers
            .get("fly-client-ip")
            .and_then(|h| h.to_str().ok())
            .unwrap_or("")
            .to_string()
    } else {
        peer.ip().to_string()
    };
    let time = now();
    live.limits.retain(|_, bucket| {
        while bucket.front().is_some_and(|t| time - t > 3600.0) {
            bucket.pop_front();
        }
        !bucket.is_empty()
    });
    let bucket = live.limits.entry(ip).or_default();
    if bucket.len() >= 20 {
        return Err(error(
            StatusCode::TOO_MANY_REQUESTS,
            "Guest creation limit reached. Try again later.",
        ));
    }
    bucket.push_back(time);
    let mut bytes = [0u8; 32];
    OsRng.fill_bytes(&mut bytes);
    let token = URL_SAFE_NO_PAD.encode(bytes);
    OsRng.fill_bytes(&mut bytes);
    let user = format!("G{}", hex::encode_upper(&bytes[..7]));
    let password = hex::encode_upper(&bytes[7..15]);
    OsRng.fill_bytes(&mut bytes);
    let verifier = backend::verifier(&user, &password, &bytes);
    let inserted =
        sqlx::query("INSERT INTO auth.account(username,salt,verifier,expansion) VALUES(?,?,?,2)")
            .bind(&user)
            .bind(bytes.as_slice())
            .bind(verifier.as_slice())
            .execute(&app.mysql)
            .await?;
    let account = inserted.last_insert_id() as i64;
    sqlx::query("INSERT INTO guests VALUES(?,?,?,?,?)")
        .bind(hex::encode(Sha256::digest(token.as_bytes())))
        .bind(account)
        .bind(&user)
        .bind(&password)
        .bind(time)
        .execute(&app.db)
        .await?;
    let g = Guest {
        account,
        username: user,
        password,
    };
    let mut response = Json(app.public(&g).await?).into_response();
    let secure = if app.origin.starts_with("https://") {
        "; Secure"
    } else {
        ""
    };
    response.headers_mut().insert(
        "set-cookie",
        HeaderValue::from_str(&format!(
            "{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000{secure}"
        ))
        .unwrap(),
    );
    Ok(response)
}
async fn credentials(State(app): State<Arc<App>>, headers: HeaderMap) -> Result<Json<Value>> {
    let g = app.guest(&headers).await?;
    Ok(Json(
        json!({"user":g.username,"pass":g.password,"host":"127.0.0.1","unattended":"1"}),
    ))
}
async fn reserve(
    State(app): State<Arc<App>>,
    headers: HeaderMap,
    Json(d): Json<Value>,
) -> Result<Json<Value>> {
    let g = app.guest(&headers).await?;
    let build = d["build"]
        .as_i64()
        .ok_or_else(|| invalid("Unknown build"))?;
    app.build(build)?;
    let _live = app.live.lock().await;
    let input = d
        .get("name")
        .map(|v| v.as_str().ok_or_else(|| invalid("Invalid name")))
        .transpose()?
        .unwrap_or("")
        .trim();
    let mut name = if input.is_empty() {
        random_name()
    } else {
        input.to_ascii_lowercase()
    };
    if !valid_name(&name) {
        return Err(invalid("Use 2–12 letters, without spaces or numbers."));
    }
    name[..1].make_ascii_uppercase();
    if name
        .to_ascii_lowercase()
        .as_bytes()
        .windows(3)
        .any(|s| s[0] == s[1] && s[1] == s[2])
    {
        return Err(invalid(
            "Names cannot contain three identical letters in a row.",
        ));
    }
    if let Some(r) = sqlx::query(
        "SELECT account,name,build,prepared FROM characters WHERE name=? COLLATE NOCASE",
    )
    .bind(&name)
    .fetch_optional(&app.db)
    .await?
    {
        if r.get::<i64, _>(0) == g.account && r.get::<i64, _>(2) == build {
            return Ok(Json(
                Character {
                    name: r.get(1),
                    build,
                    prepared: r.get(3),
                }
                .json(),
            ));
        }
        return Err(conflict("That name is already taken."));
    }
    if sqlx::query("SELECT guid FROM characters.characters WHERE name=?")
        .bind(&name)
        .fetch_optional(&app.mysql)
        .await?
        .is_some()
    {
        return Err(conflict("That name is already taken."));
    }
    let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM characters WHERE account=?")
        .bind(g.account)
        .fetch_one(&app.db)
        .await?;
    if count >= 10 {
        return Err(conflict(
            "This guest already has ten characters. Select an existing character.",
        ));
    }
    sqlx::query("INSERT INTO characters(account,name,build) VALUES(?,?,?)")
        .bind(g.account)
        .bind(&name)
        .bind(build)
        .execute(&app.db)
        .await?;
    Ok(Json(
        Character {
            name,
            build,
            prepared: 0,
        }
        .json(),
    ))
}
async fn prepare(
    State(app): State<Arc<App>>,
    headers: HeaderMap,
    Json(d): Json<Value>,
) -> Result<Json<Value>> {
    let g = app.guest(&headers).await?;
    let _live = app.live.lock().await;
    let c = app.owned(&g, &d, false).await?;
    if app.online(&g, &c).await? != app.build(c.build)?["classId"].as_i64().unwrap_or(-1) {
        return Err(conflict("Character class does not match the chosen build."));
    }
    if c.prepared != LOADOUT_VERSION {
        let r = app
            .command(&format!("botarena lobby build {} {}", c.name, c.build))
            .await?;
        if !r.contains("LOBBY_OK") {
            return Err(conflict(&r.chars().take(500).collect::<String>()));
        }
        sqlx::query("UPDATE characters SET prepared=? WHERE account=? AND name=?")
            .bind(LOADOUT_VERSION)
            .bind(g.account)
            .bind(&c.name)
            .execute(&app.db)
            .await?;
    }
    Ok(Json(json!({"ready":true})))
}
fn team_code(d: &Value) -> Result<String> {
    let code = d["code"].as_str().unwrap_or("").trim().to_ascii_uppercase();
    if code.len() != 8 || !code.bytes().all(|c| c.is_ascii_hexdigit()) {
        return Err(invalid(
            "Create a team code or enter your friend's eight-character code.",
        ));
    }
    Ok(code)
}
async fn play(
    State(app): State<Arc<App>>,
    headers: HeaderMap,
    Json(d): Json<Value>,
) -> Result<Json<Value>> {
    let g = app.guest(&headers).await?;
    let size = d["size"]
        .as_u64()
        .filter(|s| matches!(s, 2 | 3))
        .ok_or_else(|| invalid("Choose 2v2 or 3v3 and a game mode."))? as usize;
    let mode = d["mode"]
        .as_str()
        .filter(|s| matches!(*s, "watch" | "bots" | "players" | "coop"))
        .ok_or_else(|| invalid("Choose a game mode."))?;
    let arena = d
        .get("arena")
        .map(|a| a.as_str().unwrap_or(""))
        .unwrap_or("random");
    if mode == "watch" && !["random", "na", "be", "rl"].contains(&arena) {
        return Err(invalid("Choose a supported arena."));
    }
    let code = if mode == "coop" {
        Some(team_code(&d)?)
    } else {
        None
    };
    let mut live = app.live.lock().await;
    let c = app.owned(&g, &d, true).await?;
    if now() - live.last_start.get(&g.account).copied().unwrap_or(0.0) < 5.0 {
        return Err(error(
            StatusCode::TOO_MANY_REQUESTS,
            "Please wait a moment before starting another match.",
        ));
    }
    live.last_start.insert(g.account, now());
    live.cancel(g.account);
    live.games.remove(&g.account);
    app.online(&g, &c).await?;
    if mode == "players" || mode == "coop" {
        let e = Entry {
            account: g.account,
            name: c.name,
            size,
            seen: now(),
            joined: now(),
            healer: app.build(c.build)?["role"] == "Healer",
        };
        if let Some(code) = code {
            live.join_team(&code, e)?;
            app.match_team(&mut live, &code).await;
            return Ok(Json(live.status(g.account)));
        }
        live.queues.entry(size).or_default().push(e);
        app.matchmake(&mut live, size).await?;
        return Ok(Json(live.status(g.account)));
    }
    let id = if mode == "bots" {
        let result = app
            .command(&format!("botarena lobby match {size} bots {}", c.name))
            .await?;
        match_id(&result).ok_or_else(|| conflict(&result.chars().take(500).collect::<String>()))?
    } else {
        let comp = if size == 2 {
            "warrior:arms,paladin:holy"
        } else {
            "warrior:arms,dk:unholy,paladin:holy"
        };
        let before: Value = serde_json::from_str(&app.command("botarena json").await?)
            .map_err(|_| conflict("Invalid match state"))?;
        let result = app
            .command(&format!("botarena start {size} {arena} {comp} {comp}"))
            .await?;
        let after: Value = serde_json::from_str(&app.command("botarena json").await?)
            .map_err(|_| conflict("Invalid match state"))?;
        let previous: Vec<_> = before["matches"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|m| m["id"].as_u64())
            .collect();
        let id = after["matches"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|m| m["id"].as_u64())
            .filter(|id| !previous.contains(id))
            .next_back()
            .ok_or_else(|| conflict(&result.chars().take(500).collect::<String>()))?;
        let result = app
            .command(&format!("botarena spectate {} {id}", c.name))
            .await?;
        if !result.contains("now spectating") {
            return Err(conflict(&result.chars().take(500).collect::<String>()));
        }
        id
    };
    let game = json!({"state":"playing","match":id,"mode":mode,"size":size});
    live.games.insert(g.account, game.clone());
    Ok(Json(game))
}
async fn queue(State(app): State<Arc<App>>, headers: HeaderMap) -> Result<Json<Value>> {
    let g = app.guest(&headers).await?;
    let mut live = app.live.lock().await;
    live.prune_teams();
    let mut team_code = None;
    for (code, team) in &mut live.teams {
        if let Some(e) = team.iter_mut().find(|e| e.account == g.account) {
            e.seen = now();
            team_code = Some(code.clone());
        }
    }
    if let Some(code) = team_code {
        app.match_team(&mut live, &code).await;
    }
    let mut size = None;
    for q in live.queues.values_mut() {
        if let Some(e) = q.iter_mut().find(|e| e.account == g.account) {
            e.seen = now();
            size = Some(e.size);
        }
    }
    if let Some(size) = size {
        app.matchmake(&mut live, size).await?;
    }
    Ok(Json(live.status(g.account)))
}
async fn cancel_queue(State(app): State<Arc<App>>, headers: HeaderMap) -> Result<Json<Value>> {
    let g = app.guest(&headers).await?;
    app.live.lock().await.cancel(g.account);
    Ok(Json(idle()))
}
async fn leave(
    State(app): State<Arc<App>>,
    headers: HeaderMap,
    Json(d): Json<Value>,
) -> Result<Json<Value>> {
    let g = app.guest(&headers).await?;
    let mut live = app.live.lock().await;
    let c = app.owned(&g, &d, false).await?;
    live.cancel(g.account);
    live.games.remove(&g.account);
    let action = if d["logout"] == true {
        "logout"
    } else {
        "leave"
    };
    app.command(&format!("botarena lobby {action} {}", c.name))
        .await?;
    Ok(Json(idle()))
}
async fn recover(State(app): State<Arc<App>>, headers: HeaderMap) -> Result<Json<Value>> {
    let g = app.guest(&headers).await?;
    let mut live = app.live.lock().await;
    live.cancel(g.account);
    live.games.remove(&g.account);
    let names: Vec<String> =
        sqlx::query_scalar("SELECT name FROM characters.characters WHERE account=? AND online=1")
            .bind(g.account)
            .fetch_all(&app.mysql)
            .await?;
    for name in names {
        if !valid_name(&name) {
            return Err(error(
                StatusCode::SERVICE_UNAVAILABLE,
                "Invalid character state",
            ));
        }
        let r = app
            .command(&format!("botarena lobby logout {name}"))
            .await?;
        if !r.contains("LOBBY_OK") && !r.to_ascii_lowercase().contains("not online") {
            return Err(error(
                StatusCode::SERVICE_UNAVAILABLE,
                "Waiting for character logout",
            ));
        }
    }
    Ok(Json(idle()))
}
async fn health(State(app): State<Arc<App>>) -> Response {
    let ready = tokio::time::timeout(Duration::from_secs(7), async {
        for (host, port) in [(&app.login_host, 3724), (&app.world_host, 8085)] {
            tokio::net::TcpStream::connect((host.as_str(), port))
                .await
                .map_err(|_| ())?;
        }
        sqlx::query("SELECT 1")
            .execute(&app.mysql)
            .await
            .map_err(|_| ())?;
        sqlx::query("SELECT 1")
            .execute(&app.db)
            .await
            .map_err(|_| ())?;
        Ok::<_, ()>(())
    })
    .await
    .is_ok_and(|r| r.is_ok());
    (
        if ready {
            StatusCode::OK
        } else {
            StatusCode::SERVICE_UNAVAILABLE
        },
        Json(json!({"ready":ready})),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::{Body, to_bytes};
    use tower::ServiceExt;

    async fn fixture() -> (tempfile::TempDir, Arc<App>, HeaderMap) {
        let dir = tempfile::tempdir().unwrap();
        let db = open_state(&dir.path().join("guests.sqlite")).await.unwrap();
        sqlx::query("INSERT INTO guests VALUES(?,1,'GTEST','TEST',0)")
            .bind(hex::encode(Sha256::digest(b"test-token")))
            .execute(&db)
            .await
            .unwrap();
        sqlx::query("INSERT INTO characters VALUES(1,'Tester',1,2)")
            .execute(&db)
            .await
            .unwrap();
        let app = Arc::new(App {
            db,
            mysql: sqlx::mysql::MySqlPoolOptions::new()
                .connect_lazy("mysql://localhost/auth")
                .unwrap(),
            soap: backend::Soap::configured(
                "http://localhost:1".into(),
                "test".into(),
                "test".into(),
            )
            .unwrap(),
            builds: json!([{"id":1,"classId":1,"role":"Damage"}]),
            live: Mutex::new(Live::default()),
            origin: "http://localhost:8096".into(),
            login_host: "localhost".into(),
            world_host: "localhost".into(),
        });
        let mut headers = HeaderMap::new();
        headers.insert(
            "cookie",
            HeaderValue::from_static("unrelated=x; arena_guest=test-token"),
        );
        (dir, app, headers)
    }
    #[tokio::test]
    async fn iframe_directory_entry_preserves_launch_query_and_static_headers() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("index.html"), "game entry").unwrap();
        std::fs::create_dir(dir.path().join("addons")).unwrap();
        std::fs::write(
            dir.path().join("addons/index.json"),
            "[\"BotArenaSpectator\"]",
        )
        .unwrap();
        let routes = gateway_router(Router::new(), dir.path());
        let addon = routes
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/addons/index.json")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(addon.status(), StatusCode::OK);
        assert_eq!(addon.headers()["cache-control"], "no-cache");
        assert_eq!(
            to_bytes(addon.into_body(), 100).await.unwrap(),
            "[\"BotArenaSpectator\"]"
        );
        let response = routes
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/game/?recovery=1")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::TEMPORARY_REDIRECT);
        assert_eq!(
            response.headers()["location"],
            "/game/index.html?recovery=1"
        );
        let response = routes
            .oneshot(
                Request::builder()
                    .uri("/game/index.html?recovery=1")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response.headers()["cross-origin-embedder-policy"],
            "require-corp"
        );
        assert_eq!(
            to_bytes(response.into_body(), 100).await.unwrap(),
            "game entry"
        );
    }
    #[test]
    fn srp_matches_python_reference() {
        // Fixed vector independently computed with controller/arena_ctl.py.
        assert_eq!(
            hex::encode(backend::verifier("test", "password", &[0; 32])),
            "0124770777c01b1aa02c894165c8ace3968b3bd3deadfd70e3d68b804c84ab67"
        );
    }
    #[test]
    fn soap_entities_and_faults() {
        assert_eq!(
            backend::parse_soap("<Envelope><result>A &amp; B</result></Envelope>").unwrap(),
            "A & B"
        );
        assert_eq!(
            backend::parse_soap("<Envelope><faultstring>Unavailable</faultstring></Envelope>")
                .unwrap(),
            "Unavailable"
        );
        assert!(backend::parse_soap("not xml").is_err());
    }
    #[test]
    fn names_and_match_results_are_bounded() {
        for bad in ["A", "TooLongCharacter", "Tést", "a' OR 1=1", "ab cd"] {
            assert!(!valid_name(bad));
        }
        for _ in 0..1000 {
            let n = random_name();
            assert!(valid_name(&n));
            assert!(
                !n.as_bytes()
                    .windows(3)
                    .any(|s| s[0] == s[1] && s[1] == s[2])
            );
        }
        assert_eq!(match_id("LOBBY_OK match 42\n"), Some(42));
        assert_eq!(match_id("LOBBY_OK match error"), None);
    }
    #[tokio::test]
    async fn persisted_ownership_and_loadout_version() {
        let (_dir, app, headers) = fixture().await;
        let g = app.guest(&headers).await.unwrap();
        assert_eq!(
            app.owned(&g, &json!({"name":"tEsTeR"}), true)
                .await
                .unwrap()
                .name,
            "Tester"
        );
        let other = Guest {
            account: 2,
            username: "other".into(),
            password: "unused".into(),
        };
        assert_eq!(
            app.owned(&other, &json!({"name":"Tester"}), false)
                .await
                .err()
                .unwrap()
                .0,
            StatusCode::FORBIDDEN
        );
        sqlx::query("UPDATE characters SET prepared=1")
            .execute(&app.db)
            .await
            .unwrap();
        assert_eq!(
            app.owned(&g, &json!({"name":"Tester"}), true)
                .await
                .err()
                .unwrap()
                .0,
            StatusCode::FORBIDDEN
        );
        assert!(app.guest(&HeaderMap::new()).await.is_err());
        let reopened = open_state(&_dir.path().join("guests.sqlite"))
            .await
            .unwrap();
        let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM guests")
            .fetch_one(&reopened)
            .await
            .unwrap();
        assert_eq!(count, 1);
    }
    #[tokio::test]
    async fn cross_origin_api_and_game_routes_are_rejected() {
        let (_dir, app, headers) = fixture().await;
        let protected = Router::new()
            .route("/data/test", get(|| async { "asset" }))
            .route("/ws/8085", get(|| async { "socket" }))
            .route_layer(middleware::from_fn_with_state(app.clone(), game_boundary));
        let routes = gateway_router(protected, _dir.path()).route(
            "/api/credentials",
            get(credentials)
                .with_state(app.clone())
                .layer(middleware::from_fn_with_state(app.clone(), api_boundary)),
        );
        for path in [
            "/data/test",
            "/game/data/test",
            "/ws/8085",
            "/game/ws/8085",
            "/api/credentials",
        ] {
            let req = Request::builder().uri(path).body(Body::empty()).unwrap();
            assert_eq!(
                routes.clone().oneshot(req).await.unwrap().status(),
                StatusCode::UNAUTHORIZED
            );
            let mut req = Request::builder().uri(path).body(Body::empty()).unwrap();
            *req.headers_mut() = headers.clone();
            assert_eq!(
                routes.clone().oneshot(req).await.unwrap().status(),
                StatusCode::OK
            );
            let mut req = Request::builder().uri(path).body(Body::empty()).unwrap();
            *req.headers_mut() = headers.clone();
            req.headers_mut()
                .insert("origin", HeaderValue::from_static("https://evil.example"));
            assert_eq!(
                routes.clone().oneshot(req).await.unwrap().status(),
                StatusCode::FORBIDDEN
            );
        }
        let mut req = Request::builder()
            .uri("/api/credentials")
            .body(Body::empty())
            .unwrap();
        *req.headers_mut() = headers;
        let response = routes.oneshot(req).await.unwrap();
        assert_eq!(response.headers()["cache-control"], "no-store");
        let body = to_bytes(response.into_body(), 16384).await.unwrap();
        assert_eq!(
            serde_json::from_slice::<Value>(&body).unwrap()["user"],
            "GTEST"
        );
    }
    #[tokio::test]
    async fn matchmaking_prunes_stale_players_and_consumes_failed_groups() {
        let (_dir, mut app, _headers) = fixture().await;
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let calls = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let calls_for_server = calls.clone();
        let mock = Router::new().route(
            "/",
            post(move |body: String| {
                let calls = calls_for_server.clone();
                async move {
                    assert!(body.contains("botarena lobby match 2 players"));
                    calls.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                    "<Envelope><result>LOBBY_ERROR unavailable</result></Envelope>"
                }
            }),
        );
        let server = tokio::spawn(async move {
            axum::serve(listener, mock).await.unwrap();
        });
        Arc::get_mut(&mut app).unwrap().soap =
            backend::Soap::configured(format!("http://{addr}/"), "test".into(), "test".into())
                .unwrap();
        let mut live = Live::default();
        let entries = (0..4)
            .map(|i| Entry {
                account: i,
                name: format!("Player{}", (b'A' + i as u8) as char),
                size: 2,
                seen: if i == 0 { now() - 30.0 } else { now() },
                joined: now(),
                healer: false,
            })
            .collect();
        live.queues.insert(2, entries);
        app.matchmake(&mut live, 2).await.unwrap();
        assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 0);
        assert_eq!(live.status(0), idle());
        live.queues.get_mut(&2).unwrap().push(Entry {
            account: 4,
            name: "PlayerE".into(),
            size: 2,
            seen: now(),
            joined: now(),
            healer: false,
        });
        app.matchmake(&mut live, 2).await.unwrap();
        assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 1);
        for i in 1..5 {
            assert_eq!(live.status(i)["state"], "error");
        }
        app.matchmake(&mut live, 2).await.unwrap();
        assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 1);
        server.abort();
    }
    #[tokio::test]
    async fn team_match_is_scoped_atomic_and_never_retried() {
        let (_dir, mut app, _) = fixture().await;
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let calls = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let counter = calls.clone();
        let mock = Router::new().route(
            "/",
            post(move |body: String| {
                let counter = counter.clone();
                async move {
                    assert!(body.contains("botarena lobby match 3 bots PlayerA PlayerB"));
                    counter.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                    "<Envelope><result>LOBBY_OK match 42</result></Envelope>"
                }
            }),
        );
        let server = tokio::spawn(async move {
            axum::serve(listener, mock).await.unwrap();
        });
        Arc::get_mut(&mut app).unwrap().soap =
            backend::Soap::configured(format!("http://{addr}/"), "test".into(), "test".into())
                .unwrap();
        let entry = |account, name: &str, size| Entry {
            account,
            name: name.into(),
            size,
            seen: now(),
            joined: now(),
            healer: false,
        };
        let mut live = Live::default();
        live.join_team("1234ABCD", entry(1, "PlayerA", 3)).unwrap();
        live.join_team("1234ABCD", entry(1, "PlayerA", 3)).unwrap();
        app.match_team(&mut live, "1234ABCD").await;
        assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 0);
        assert!(live.join_team("1234ABCD", entry(2, "PlayerB", 2)).is_err());
        live.join_team("ABCD1234", entry(3, "PlayerC", 3)).unwrap();
        live.join_team("1234ABCD", entry(2, "PlayerB", 3)).unwrap();
        app.match_team(&mut live, "1234ABCD").await;
        assert_eq!(live.status(1)["match"], 42);
        assert_eq!(live.status(1), live.status(2));
        assert_eq!(live.status(3)["waiting"], 1);
        assert!(live.join_team("1234ABCD", entry(4, "PlayerD", 3)).is_err());
        app.match_team(&mut live, "1234ABCD").await;
        assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 1);
        // An unavailable transport is an uncertain start: consume both entries once.
        server.abort();
        live.join_team("DEADBEEF", entry(1, "PlayerA", 3)).unwrap();
        live.join_team("DEADBEEF", entry(2, "PlayerB", 3)).unwrap();
        app.match_team(&mut live, "DEADBEEF").await;
        assert_eq!(live.status(1)["state"], "error");
        assert_eq!(live.status(2)["state"], "error");
        assert!(live.used_codes.contains_key("DEADBEEF"));
        live.cancel(3);
        assert_eq!(live.status(3), idle());
        live.join_team("DEAD1234", entry(5, "PlayerE", 2)).unwrap();
        live.teams.get_mut("DEAD1234").unwrap()[0].seen = now() - 21.0;
        live.prune_teams();
        assert_eq!(live.status(5), idle());
        assert_eq!(
            team_code(&json!({"code":" abcd1234 "})).unwrap(),
            "ABCD1234"
        );
        assert!(team_code(&json!({"code":"abc;shutdown"})).is_err());
    }
    #[test]
    fn queues_balance_healers_and_cancel_only_owner() {
        let mut entries = Vec::new();
        for (i, name) in ["Dpsone", "HealOne", "HealTwo", "Dpstwo"]
            .iter()
            .enumerate()
        {
            entries.push(Entry {
                account: i as i64,
                name: name.to_string(),
                size: 2,
                seen: now(),
                joined: now(),
                healer: i == 1 || i == 2,
            });
        }
        assert_eq!(team_names(&entries), "HealOne Dpsone HealTwo Dpstwo");
        let mut live = Live::default();
        live.queues.insert(2, entries);
        live.cancel(1);
        assert_eq!(live.status(1), idle());
        assert_eq!(live.status(0)["waiting"], 3);
    }
}
