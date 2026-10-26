//! Native integration peer: dedicated guest credentials come only from environment variables.
use anyhow::{Result, bail};
use benilla_protocol::{WorldSession, SessionEvent, decode};
use benilla_protocol::messages::CharCreateReq;
use std::{env, time::{Instant,Duration}};
fn main()->Result<()> {
 let user=env::var("WOW_USER")?;let pass=env::var("WOW_PASS")?;let name=env::var("WOW_CHAR")?;
 let auth=benilla_protocol::logon("127.0.0.1",&user,&pass)?;
 let mut s=WorldSession::connect("127.0.0.1:8085",&user,auth.session_key,auth.realms[0].id)?;
 let mut chars=s.char_enum()?;
 if !chars.iter().any(|c|c.name==name){
  let req=CharCreateReq{name:name.clone(),race:env::var("PROBE_RACE")?.parse()?,class:env::var("PROBE_CLASS")?.parse()?,gender:0,skin:0,face:0,hair_style:0,hair_color:0,facial_hair:0};
  let result=s.create_character(&req)?;
  if result!=benilla_protocol::messages::CHAR_CREATE_SUCCESS {bail!("create result {result}")}
  chars=s.char_enum()?;
 }
 let c=chars.iter().find(|c|c.name==name).unwrap();let guid=c.guid;
 s.player_login(guid)?;s.set_active_mover(guid)?;s.set_read_timeout(Some(Duration::from_millis(500)))?;
 println!("CONNECTED {name}");
 let until=Instant::now()+Duration::from_secs(env::var("PROBE_SECONDS").unwrap_or("240".into()).parse()?);
 while Instant::now()<until {
  if let Ok(packet)=s.recv(){for e in decode(packet){match e {
   SessionEvent::Worldport{map_id,needs_ack,..}=>{if needs_ack{s.worldport_ack()?;}println!("MAP {name} {map_id}");},
   SessionEvent::Teleport{guid,counter,..}=>{s.teleport_ack(guid,counter)?;},
   _=>{}
  }}}
 }
 Ok(())
}
