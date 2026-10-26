fn main() {
    println!("cargo:rerun-if-env-changed=STORMLIB_DIR");
    if let Ok(path) = std::env::var("STORMLIB_DIR") {
        println!("cargo:rustc-link-search=native={path}/lib");
    } else if cfg!(target_os = "macos")
        && let Ok(out) = std::process::Command::new("brew")
            .args(["--prefix", "stormlib"])
            .output()
        && out.status.success()
    {
        println!(
            "cargo:rustc-link-search=native={}/lib",
            String::from_utf8_lossy(&out.stdout).trim()
        );
    }
    println!("cargo:rustc-link-lib=storm");
}
