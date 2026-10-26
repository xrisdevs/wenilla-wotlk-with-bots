use anyhow::{Context, Result};
use num_bigint::BigUint;
use sha1::{Digest, Sha1};
use sqlx::{MySqlPool, mysql::MySqlConnectOptions};
use std::time::Duration;

pub fn env(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.into())
}

pub async fn database() -> Result<MySqlPool> {
    let options = MySqlConnectOptions::new()
        .host(&env("ARENA_DB_HOST", "127.0.0.1"))
        .port(env("ARENA_DB_PORT", "3306").parse()?)
        .username(&env("ARENA_DB_USER", "trinity"))
        .password(&std::env::var("ARENA_DB_PASSWORD").context("Set ARENA_DB_PASSWORD")?)
        .database("auth");
    Ok(sqlx::mysql::MySqlPoolOptions::new()
        .max_connections(4)
        .acquire_timeout(Duration::from_secs(10))
        .connect_with(options)
        .await?)
}

// TrinityCore SRP6 stores the exponent and padded verifier in little-endian order.
pub fn verifier(user: &str, password: &str, salt: &[u8; 32]) -> [u8; 32] {
    let identity = Sha1::digest(format!(
        "{}:{}",
        user.to_ascii_uppercase(),
        password.to_ascii_uppercase()
    ));
    let mut hash = Sha1::new();
    hash.update(salt);
    hash.update(identity);
    let x = BigUint::from_bytes_le(&hash.finalize());
    let n = BigUint::parse_bytes(
        b"894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7",
        16,
    )
    .unwrap();
    let bytes = BigUint::from(7u8).modpow(&x, &n).to_bytes_le();
    let mut result = [0; 32];
    result[..bytes.len()].copy_from_slice(&bytes);
    result
}

pub struct Soap {
    client: reqwest::Client,
    url: String,
    user: String,
    password: String,
}
impl Soap {
    pub fn new() -> Result<Self> {
        Self::configured(
            env("ARENA_SOAP_URL", "http://127.0.0.1:7878/"),
            env("ARENA_SOAP_USER", "ARENAOP"),
            std::env::var("ARENA_SOAP_PASS").context("Set ARENA_SOAP_PASS")?,
        )
    }
    pub fn configured(url: String, user: String, password: String) -> Result<Self> {
        Ok(Self {
            client: reqwest::Client::builder()
                .timeout(Duration::from_secs(30))
                .build()?,
            url,
            user,
            password,
        })
    }
    pub async fn command(&self, command: &str) -> Result<String> {
        let escaped = command
            .replace('&', "&amp;")
            .replace('<', "&lt;")
            .replace('>', "&gt;");
        let body = format!(
            r#"<?xml version="1.0" encoding="utf-8"?><SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns1="urn:TC"><SOAP-ENV:Body><ns1:executeCommand><command>{escaped}</command></ns1:executeCommand></SOAP-ENV:Body></SOAP-ENV:Envelope>"#
        );
        let response = self
            .client
            .post(&self.url)
            .basic_auth(&self.user, Some(&self.password))
            .header("Content-Type", "text/xml; charset=utf-8")
            .body(body)
            .send()
            .await?;
        // SOAP faults can use an HTTP error status. Parse the bounded body either way.
        let mut response = response;
        let mut bytes = Vec::new();
        while let Some(chunk) = response.chunk().await? {
            anyhow::ensure!(
                bytes.len() + chunk.len() <= 2 * 1024 * 1024,
                "SOAP response too large"
            );
            bytes.extend_from_slice(&chunk);
        }
        parse_soap(std::str::from_utf8(&bytes)?)
    }
}
pub fn parse_soap(body: &str) -> Result<String> {
    let doc = roxmltree::Document::parse(body)?;
    for tag in ["result", "faultstring"] {
        if let Some(node) = doc
            .descendants()
            .find(|n| n.is_element() && n.tag_name().name() == tag)
        {
            return Ok(node.text().unwrap_or_default().into());
        }
    }
    anyhow::bail!("Missing SOAP result")
}
