use std::{path::PathBuf, sync::Arc};
use wenilla_arena_host::{App, backend::env};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .init();
    let home = PathBuf::from(env("ARENA_LOBBY_HOME", "artifacts/lobby/state"));
    let app = App::open(
        &home,
        &PathBuf::from(env("ARENA_BUILDS", "controller/lobby/builds.json")),
    )
    .await?;
    let chain = Arc::new(benilla_formats::Chain::open(&PathBuf::from(env(
        "WOW_DATA",
        "/game-data",
    )))?);
    let router = wenilla_arena_host::router(
        app,
        chain,
        &PathBuf::from(env("ARENA_WWW", "client/benilla-src/web/dist")),
        &PathBuf::from(env("ARENA_LOBBY_UI", "client/lobby")),
    );
    let bind = format!(
        "{}:{}",
        env("ARENA_BIND", "127.0.0.1"),
        env("ARENA_PORT", "8090")
    );
    let listener = tokio::net::TcpListener::bind(&bind).await?;
    tracing::info!(%bind, "Arena host ready: lobby, assets and game sockets in one process");
    axum::serve(
        listener,
        router.into_make_service_with_connect_info::<std::net::SocketAddr>(),
    )
    .with_graceful_shutdown(shutdown())
    .await?;
    Ok(())
}
async fn shutdown() {
    #[cfg(unix)]
    {
        let mut terminate =
            tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
                .expect("SIGTERM handler");
        tokio::select! { _ = tokio::signal::ctrl_c() => {}, _ = terminate.recv() => {} }
    }
    #[cfg(not(unix))]
    {
        let _ = tokio::signal::ctrl_c().await;
    }
}
