/*
 * BotArena: bot-vs-bot arena matches with a spectator, built on top of NPCBots.
 *
 * Commands (GM / SOAP console):
 *   .botarena start [2|3|5] [na|be|rl|ds|rv|random] [compA] [compH]
 *   .botarena stop
 *   .botarena status | json
 *   .botarena spectate [player]
 *   .botarena cam <1-10|name|auto|off> [player]
 *   .botarena auto <on|off> [delaySeconds]
 *   .botarena comps
 *
 * Comps are "class:spec,class:spec,..." or a preset name (see Presets below).
 */

#include "ScriptMgr.h"
#include "Arena.h"
#include "Battleground.h"
#include "BattlegroundMgr.h"
#include "Chat.h"
#include "ChatCommand.h"
#include "ChatPackets.h"
#include "Creature.h"
#include "DBCStores.h"
#include "GameTime.h"
#include "Log.h"
#include "Map.h"
#include "MapInstanced.h"
#include "MapManager.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "RBAC.h"
#include "SharedDefines.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellAuras.h"
#include "SpellAuraEffects.h"
#include "BattlegroundScore.h"
#include "DatabaseEnv.h"
#include "Item.h"
#include "ItemTemplate.h"
#include "ObjectMgr.h"
#include "Config.h"
#include <cmath>
#include <deque>
#include <fstream>
#include <memory>
#include "StringConvert.h"
#include "StringFormat.h"
#include "Object.h"
#include "Random.h"
#include <cstring>
#include "World.h"
#include "WorldSession.h"
#include "Trainer.h"
#include "Pet.h"
#include "lobby_builds.h"
#include "bot_ai.h"
#include "botcommon.h"
#include "botdatamgr.h"
#include "botmgr.h"
#include "botspell.h"
#include "botwanderful.h"

#include <algorithm>
#include <map>
#include <random>
#include <sstream>
#include <vector>

using namespace Trinity::ChatCommands;

namespace
{
    struct ClassSpec
    {
        uint8 cls = 0;
        uint8 spec = 0;
    };

    struct ArenaBot
    {
        uint32 entry = 0;
        ObjectGuid guid;
        uint32 team = 0;          // ALLIANCE / HORDE
        ClassSpec cs;
        std::string name;
        bool added = false;       // added to the Battleground object
        bool setupVerified = false;
        std::map<uint32, uint32> casts;
        // ArenaBrain state
        uint32 kiteUntilMs = 0;
        uint32 lastKiteMs = 0;
        uint32 lastStealthMs = 0;
    };

    struct Preset
    {
        char const* name;
        char const* comp;
        char const* desc;
    };

    // Well-known WotLK 3v3 compositions.
    Preset const Presets[] =
    {
        { "rmp",         "rogue:sub,mage:frost,priest:disc",          "Rogue/Mage/Priest" },
        { "tsg",         "warrior:arms,dk:unholy,paladin:holy",       "Warrior/DK/Holy Paladin" },
        { "beastcleave", "hunter:bm,shaman:enh,shaman:resto",         "Hunter/Enh Shaman/Resto Shaman" },
        { "wls",         "warrior:arms,warlock:aff,shaman:resto",     "Warrior/Warlock/Resto Shaman" },
        { "shadowplay",  "priest:shadow,warlock:aff,shaman:resto",    "Shadow Priest/Warlock/Resto Shaman" },
        { "lsd",         "warlock:aff,shaman:ele,druid:resto",        "Warlock/Ele Shaman/Resto Druid" },
        { "kittycleave", "druid:feral,warrior:arms,paladin:holy",     "Feral/Warrior/Holy Paladin" },
        { "pmr",         "paladin:holy,mage:frost,rogue:sub",         "Holy Paladin/Mage/Rogue" },
        { "thugcleave",  "hunter:mm,rogue:sub,priest:disc",           "Hunter/Rogue/Disc Priest" },
        { "mld",         "mage:frost,warlock:aff,druid:resto",        "Mage/Warlock/Resto Druid" },
        { "rls",         "rogue:sub,warlock:aff,shaman:resto",        "Rogue/Warlock/Resto Shaman" },
        { "wmp",         "warrior:arms,mage:frost,priest:disc",       "Warrior/Mage/Priest" },
        // 2v2
        { "rp",          "rogue:sub,priest:disc",                     "Rogue/Disc Priest (2v2)" },
        { "ww",          "warrior:arms,druid:resto",                  "Warrior/Resto Druid (2v2)" },
        { "ml",          "mage:frost,warlock:aff",                    "Mage/Warlock (2v2)" },
        { "dkh",         "dk:unholy,paladin:holy",                    "DK/Holy Paladin (2v2)" },
    };

    char const* ClassName(uint8 cls)
    {
        switch (cls)
        {
            case BOT_CLASS_WARRIOR: return "warrior";
            case BOT_CLASS_PALADIN: return "paladin";
            case BOT_CLASS_HUNTER: return "hunter";
            case BOT_CLASS_ROGUE: return "rogue";
            case BOT_CLASS_PRIEST: return "priest";
            case BOT_CLASS_DEATH_KNIGHT: return "dk";
            case BOT_CLASS_SHAMAN: return "shaman";
            case BOT_CLASS_MAGE: return "mage";
            case BOT_CLASS_WARLOCK: return "warlock";
            case BOT_CLASS_DRUID: return "druid";
            default: return "unknown";
        }
    }

    char const* SpecName(uint8 spec)
    {
        switch (spec)
        {
            case BOT_SPEC_WARRIOR_ARMS: return "arms";
            case BOT_SPEC_WARRIOR_FURY: return "fury";
            case BOT_SPEC_WARRIOR_PROTECTION: return "prot";
            case BOT_SPEC_PALADIN_HOLY: return "holy";
            case BOT_SPEC_PALADIN_PROTECTION: return "prot";
            case BOT_SPEC_PALADIN_RETRIBUTION: return "ret";
            case BOT_SPEC_HUNTER_BEASTMASTERY: return "bm";
            case BOT_SPEC_HUNTER_MARKSMANSHIP: return "mm";
            case BOT_SPEC_HUNTER_SURVIVAL: return "surv";
            case BOT_SPEC_ROGUE_ASSASINATION: return "assa";
            case BOT_SPEC_ROGUE_COMBAT: return "combat";
            case BOT_SPEC_ROGUE_SUBTLETY: return "sub";
            case BOT_SPEC_PRIEST_DISCIPLINE: return "disc";
            case BOT_SPEC_PRIEST_HOLY: return "holy";
            case BOT_SPEC_PRIEST_SHADOW: return "shadow";
            case BOT_SPEC_DK_BLOOD: return "blood";
            case BOT_SPEC_DK_FROST: return "frost";
            case BOT_SPEC_DK_UNHOLY: return "unholy";
            case BOT_SPEC_SHAMAN_ELEMENTAL: return "ele";
            case BOT_SPEC_SHAMAN_ENHANCEMENT: return "enh";
            case BOT_SPEC_SHAMAN_RESTORATION: return "resto";
            case BOT_SPEC_MAGE_ARCANE: return "arcane";
            case BOT_SPEC_MAGE_FIRE: return "fire";
            case BOT_SPEC_MAGE_FROST: return "frost";
            case BOT_SPEC_WARLOCK_AFFLICTION: return "aff";
            case BOT_SPEC_WARLOCK_DEMONOLOGY: return "demo";
            case BOT_SPEC_WARLOCK_DESTRUCTION: return "destro";
            case BOT_SPEC_DRUID_BALANCE: return "balance";
            case BOT_SPEC_DRUID_FERAL: return "feral";
            case BOT_SPEC_DRUID_RESTORATION: return "resto";
            default: return "default";
        }
    }

    std::string Lower(std::string s)
    {
        std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::tolower(c); });
        return s;
    }

    uint8 ParseClass(std::string const& t)
    {
        if (t == "warrior" || t == "war" || t == "warr") return BOT_CLASS_WARRIOR;
        if (t == "paladin" || t == "pala" || t == "pal" || t == "paly") return BOT_CLASS_PALADIN;
        if (t == "hunter" || t == "hunt") return BOT_CLASS_HUNTER;
        if (t == "rogue" || t == "rog") return BOT_CLASS_ROGUE;
        if (t == "priest" || t == "pri") return BOT_CLASS_PRIEST;
        if (t == "dk" || t == "deathknight" || t == "death_knight") return BOT_CLASS_DEATH_KNIGHT;
        if (t == "shaman" || t == "sham" || t == "shm") return BOT_CLASS_SHAMAN;
        if (t == "mage") return BOT_CLASS_MAGE;
        if (t == "warlock" || t == "lock" || t == "wl") return BOT_CLASS_WARLOCK;
        if (t == "druid" || t == "dru") return BOT_CLASS_DRUID;
        return 0;
    }

    uint8 ParseSpec(uint8 cls, std::string const& t)
    {
        if (t.empty()) return 0;
        switch (cls)
        {
            case BOT_CLASS_WARRIOR:
                if (t == "arms") return BOT_SPEC_WARRIOR_ARMS;
                if (t == "fury") return BOT_SPEC_WARRIOR_FURY;
                if (t == "prot") return BOT_SPEC_WARRIOR_PROTECTION;
                break;
            case BOT_CLASS_PALADIN:
                if (t == "holy") return BOT_SPEC_PALADIN_HOLY;
                if (t == "prot") return BOT_SPEC_PALADIN_PROTECTION;
                if (t == "ret") return BOT_SPEC_PALADIN_RETRIBUTION;
                break;
            case BOT_CLASS_HUNTER:
                if (t == "bm") return BOT_SPEC_HUNTER_BEASTMASTERY;
                if (t == "mm") return BOT_SPEC_HUNTER_MARKSMANSHIP;
                if (t == "surv" || t == "sv") return BOT_SPEC_HUNTER_SURVIVAL;
                break;
            case BOT_CLASS_ROGUE:
                if (t == "assa" || t == "mut") return BOT_SPEC_ROGUE_ASSASINATION;
                if (t == "combat") return BOT_SPEC_ROGUE_COMBAT;
                if (t == "sub") return BOT_SPEC_ROGUE_SUBTLETY;
                break;
            case BOT_CLASS_PRIEST:
                if (t == "disc") return BOT_SPEC_PRIEST_DISCIPLINE;
                if (t == "holy") return BOT_SPEC_PRIEST_HOLY;
                if (t == "shadow") return BOT_SPEC_PRIEST_SHADOW;
                break;
            case BOT_CLASS_DEATH_KNIGHT:
                if (t == "blood") return BOT_SPEC_DK_BLOOD;
                if (t == "frost") return BOT_SPEC_DK_FROST;
                if (t == "unholy") return BOT_SPEC_DK_UNHOLY;
                break;
            case BOT_CLASS_SHAMAN:
                if (t == "ele") return BOT_SPEC_SHAMAN_ELEMENTAL;
                if (t == "enh") return BOT_SPEC_SHAMAN_ENHANCEMENT;
                if (t == "resto") return BOT_SPEC_SHAMAN_RESTORATION;
                break;
            case BOT_CLASS_MAGE:
                if (t == "arcane") return BOT_SPEC_MAGE_ARCANE;
                if (t == "fire") return BOT_SPEC_MAGE_FIRE;
                if (t == "frost") return BOT_SPEC_MAGE_FROST;
                break;
            case BOT_CLASS_WARLOCK:
                if (t == "aff") return BOT_SPEC_WARLOCK_AFFLICTION;
                if (t == "demo") return BOT_SPEC_WARLOCK_DEMONOLOGY;
                if (t == "destro") return BOT_SPEC_WARLOCK_DESTRUCTION;
                break;
            case BOT_CLASS_DRUID:
                if (t == "balance" || t == "boomkin") return BOT_SPEC_DRUID_BALANCE;
                if (t == "feral") return BOT_SPEC_DRUID_FERAL;
                if (t == "resto") return BOT_SPEC_DRUID_RESTORATION;
                break;
            default:
                break;
        }
        return 0;
    }

    // "rogue:sub,mage:frost,priest:disc" or preset name -> vector<ClassSpec>
    bool ParseComp(std::string comp, std::vector<ClassSpec>& out, std::string& err)
    {
        comp = Lower(comp);
        for (Preset const& p : Presets)
            if (comp == p.name)
            {
                comp = p.comp;
                break;
            }

        out.clear();
        std::stringstream ss(comp);
        std::string tok;
        while (std::getline(ss, tok, ','))
        {
            if (tok.empty())
                continue;
            std::string c = tok, s;
            if (size_t pos = tok.find(':'); pos != std::string::npos)
            {
                c = tok.substr(0, pos);
                s = tok.substr(pos + 1);
            }
            ClassSpec cs;
            cs.cls = ParseClass(c);
            if (!cs.cls)
            {
                err = "unknown class '" + c + "'";
                return false;
            }
            cs.spec = ParseSpec(cs.cls, s);
            if (!s.empty() && !cs.spec)
            {
                err = "unknown spec '" + s + "' for class " + c;
                return false;
            }
            out.push_back(cs);
        }
        if (out.empty())
        {
            err = "empty comp";
            return false;
        }
        return true;
    }

    std::vector<Preset const*> PresetsForSize(size_t n)
    {
        std::vector<Preset const*> res;
        for (Preset const& p : Presets)
        {
            size_t count = 1 + std::count(p.comp, p.comp + strlen(p.comp), ',');
            if (count == n)
                res.push_back(&p);
        }
        return res;
    }

    bool ParseArena(std::string t, BattlegroundTypeId& out)
    {
        t = Lower(t);
        if (t == "na" || t == "nagrand") out = BATTLEGROUND_NA;
        else if (t == "be" || t == "blade" || t == "blades") out = BATTLEGROUND_BE;
        else if (t == "rl" || t == "ruins" || t == "lordaeron") out = BATTLEGROUND_RL;
        else if (t == "ds" || t == "dalaran" || t == "sewers") out = BATTLEGROUND_DS;
        else if (t == "rv" || t == "ring" || t == "valor") out = BATTLEGROUND_RV;
        else if (t == "random" || t == "rand" || t == "aa" || t == "any") out = BATTLEGROUND_AA;
        else return false;
        return true;
    }

    char const* ArenaName(BattlegroundTypeId id)
    {
        switch (id)
        {
            case BATTLEGROUND_NA: return "Nagrand Arena";
            case BATTLEGROUND_BE: return "Blade's Edge Arena";
            case BATTLEGROUND_RL: return "Ruins of Lordaeron";
            case BATTLEGROUND_DS: return "Dalaran Sewers";
            case BATTLEGROUND_RV: return "Ring of Valor";
            default: return "Arena";
        }
    }

    BattlegroundTypeId RandomArena()
    {
        // BotArena.RandomArenas = "na,be,rl" (rv excluded by default: its elevators produce NaN bot positions)
        static std::vector<BattlegroundTypeId> pool;
        if (pool.empty())
        {
            std::string cfg = Lower(sConfigMgr->GetStringDefault("BotArena.RandomArenas", "na,be,rl"));
            std::stringstream ss(cfg);
            std::string tok;
            while (std::getline(ss, tok, ','))
            {
                BattlegroundTypeId id;
                if (ParseArena(tok, id) && id != BATTLEGROUND_AA)
                    pool.push_back(id);
            }
            if (pool.empty())
                pool = { BATTLEGROUND_NA, BATTLEGROUND_BE, BATTLEGROUND_RL };
        }
        std::vector<BattlegroundTypeId> avail;
        for (BattlegroundTypeId id : pool)
            if (sBattlegroundMgr->GetBattlegroundTemplate(id))
                avail.push_back(id);
        if (avail.empty())
            return BATTLEGROUND_NA;
        return avail[urand(0, avail.size() - 1)];
    }

    std::string Json(std::string const& s)
    {
        std::string o = "\"";
        for (char c : s)
        {
            if (c == '"' || c == '\\') { o += '\\'; o += c; }
            else if (c == '\n') o += "\\n";
            else o += c;
        }
        return o + "\"";
    }
}


constexpr uint32 SPECTATOR_DISPLAY_ID = 11686; // "Invisible Trigger"
constexpr uint32 SPELL_ROGUE_STEALTH = 1784;
constexpr uint32 SPELL_DRUID_PROWL = 5215;

// ------------------------------------------------------------------------------------------------
// ArenaBrain parameters: tunable from /conf/arenabrain.params (key = value) and `.botarena brain set`.
// These are the knobs the headless farm optimises.
// ------------------------------------------------------------------------------------------------
struct BrainParams
{
    float healerBias      = 25.0f;  // kill-target score bonus (as hp%) for enemy healers
    float ccBonus         = 15.0f;  // bonus for targets currently crowd-controlled
    float distWeight      = 0.6f;   // score penalty per yard of average distance to our melee
    float swapMargin      = 12.0f;  // a new target must beat the current one by this many points
    uint32 minTargetHoldMs = 4000;  // never swap faster than this
    float kiteTrigger     = 7.0f;   // ranged/healer bots start kiting when an enemy melee is this close
    float kiteDist        = 14.0f;  // how far the kite step goes
    uint32 kiteStayMs     = 2500;   // how long the kite position is held
    uint32 kiteCooldownMs = 6000;   // minimum time between kite steps
    float kiteHealthMin   = 0.0f;   // only kite above this hp% (0 = always)
    bool stealthOpeners   = true;   // rogues/ferals open from stealth
    bool focusFire        = true;   // enforce a shared kill target per team
    uint32 tickMs         = 500;

    std::string Show() const
    {
        return Trinity::StringFormat(
            "healerBias={} ccBonus={} distWeight={} swapMargin={} minTargetHoldMs={} kiteTrigger={} kiteDist={} kiteStayMs={} kiteCooldownMs={} kiteHealthMin={} stealthOpeners={} focusFire={} tickMs={}",
            healerBias, ccBonus, distWeight, swapMargin, minTargetHoldMs, kiteTrigger, kiteDist, kiteStayMs, kiteCooldownMs, kiteHealthMin, stealthOpeners ? 1 : 0, focusFire ? 1 : 0, tickMs);
    }

    bool Set(std::string key, std::string const& value)
    {
        key = Lower(key);
        auto f = [&](float& v) { if (Optional<float> x = Trinity::StringTo<float>(value)) { v = *x; return true; } return false; };
        auto u = [&](uint32& v) { if (Optional<uint32> x = Trinity::StringTo<uint32>(value)) { v = *x; return true; } return false; };
        auto b = [&](bool& v) { std::string lv = Lower(value); v = (lv == "1" || lv == "true" || lv == "on"); return true; };
        if (key == "healerbias") return f(healerBias);
        if (key == "ccbonus") return f(ccBonus);
        if (key == "distweight") return f(distWeight);
        if (key == "swapmargin") return f(swapMargin);
        if (key == "mintargetholdms") return u(minTargetHoldMs);
        if (key == "kitetrigger") return f(kiteTrigger);
        if (key == "kitedist") return f(kiteDist);
        if (key == "kitestayms") return u(kiteStayMs);
        if (key == "kitecooldownms") return u(kiteCooldownMs);
        if (key == "kitehealthmin") return f(kiteHealthMin);
        if (key == "stealthopeners") return b(stealthOpeners);
        if (key == "focusfire") return b(focusFire);
        if (key == "tickms") return u(tickMs);
        return false;
    }

    // "key = value" lines, '#' comments
    uint32 LoadFile(std::string const& path)
    {
        std::ifstream in(path);
        if (!in)
            return 0;
        uint32 n = 0;
        std::string line;
        while (std::getline(in, line))
        {
            size_t hash = line.find('#');
            if (hash != std::string::npos) line = line.substr(0, hash);
            size_t eq = line.find('=');
            if (eq == std::string::npos) continue;
            std::string k = line.substr(0, eq), v = line.substr(eq + 1);
            auto trim = [](std::string& s) { while (!s.empty() && isspace((unsigned char)s.back())) s.pop_back(); while (!s.empty() && isspace((unsigned char)s.front())) s.erase(0, 1); };
            trim(k); trim(v);
            if (!k.empty() && Set(k, v)) ++n;
        }
        return n;
    }
};

class BotArenaMgr
{
public:
    enum class State { Idle, Starting, Running, Ended };

    struct CastEvent
    {
        uint32 seq;
        uint32 timeMs;
        uint32 casterIdx;
        uint32 targetIdx;
        uint32 spellId;
    };

    struct Match
    {
        uint32 id = 0;
        State state = State::Idle;
        uint32 instanceId = 0;
        BattlegroundTypeId typeId = BATTLEGROUND_TYPE_NONE;
        uint32 mapId = 0;
        uint8 arenaType = 3;
        std::string compAStr, compHStr;
        std::vector<ArenaBot> bots;
        std::vector<ObjectGuid> humans;
        std::deque<CastEvent> events;
        uint32 eventSeq = 0;
        PvPTeamId winner = PVP_TEAM_NEUTRAL;
        bool endRecorded = false;
        uint32 startedMs = 0;
        uint32 endedAtMs = 0;
        uint32 durationMs = 0;
        bool fromBatch = false;
        bool logged = false;
        uint32 brainTimer = 0;
        // brain: per-team kill target (index 0 = ALLIANCE team, 1 = HORDE team)
        ObjectGuid killTarget[2];
        uint32 killTargetSinceMs[2] = { 0, 0 };
        std::string resultLine;

        Battleground* GetBG() const { return sBattlegroundMgr->GetBattleground(instanceId, typeId); }
        ArenaBot* FindByEntry(uint32 entry) { for (ArenaBot& b : bots) if (b.entry == entry) return &b; return nullptr; }
        ArenaBot* FindByGuid(ObjectGuid guid) { for (ArenaBot& b : bots) if (b.guid == guid) return &b; return nullptr; }
        bool Running() const { return state == State::Starting || state == State::Running; }
    };

    struct Spectator
    {
        ObjectGuid guid;
        uint32 matchId = 0;
        bool camAuto = false;
        bool initialViewPending = false;
        uint32 camLastMs = 0;
        uint32 lastSentSeq = 0;
        uint32 rejoinAtMs = 0;
    };

    struct Batch
    {
        bool active = false;
        uint32 total = 0;
        uint32 started = 0;
        uint32 done = 0;
        uint32 winsA = 0;
        uint32 winsH = 0;
        uint32 draws = 0;
        uint32 concurrency = 1;
        uint8 type = 3;
        BattlegroundTypeId arena = BATTLEGROUND_AA;
        std::string compA, compH; // preset / explicit / "random"
        uint32 startedAtMs = 0;
    };

    static BotArenaMgr* instance()
    {
        static BotArenaMgr inst;
        return &inst;
    }

    // ---------------------------------------------------------------- gear sets (botarena_gear / botarena_gear_gems)
    struct GearPiece { uint32 item = 0; uint32 enchant = 0; };
    struct GearSet { std::map<uint8, GearPiece> pieces; uint32 gemRed = 0, gemYellow = 0, gemBlue = 0, gemMeta = 0; };

    uint32 LoadGear()
    {
        _gear.clear();
        if (QueryResult r = WorldDatabase.Query("SELECT class, spec, slot, item, enchant FROM botarena_gear"))
        {
            do
            {
                Field* f = r->Fetch();
                GearSet& gs = _gear[{ f[0].GetUInt8(), f[1].GetUInt8() }];
                GearPiece& gp = gs.pieces[f[2].GetUInt8()];
                gp.item = f[3].GetUInt32();
                gp.enchant = f[4].GetUInt32();
                if (!sObjectMgr->GetItemTemplate(gp.item))
                    TC_LOG_ERROR("npcbots", "BotArena gear: unknown item {} (class {} spec {} slot {})", gp.item, f[0].GetUInt8(), f[1].GetUInt8(), f[2].GetUInt8());
                if (gp.enchant)
                {
                    if (SpellItemEnchantmentEntry const* e = sSpellItemEnchantmentStore.LookupEntry(gp.enchant))
                        _enchantNames[gp.enchant] = e->Name[0] ? e->Name[0] : "?";
                    else
                    {
                        TC_LOG_ERROR("npcbots", "BotArena gear: unknown enchant {} for item {}", gp.enchant, gp.item);
                        gp.enchant = 0;
                    }
                }
            } while (r->NextRow());
        }
        if (QueryResult r = WorldDatabase.Query("SELECT class, spec, gem_red, gem_yellow, gem_blue, gem_meta FROM botarena_gear_gems"))
        {
            do
            {
                Field* f = r->Fetch();
                GearSet& gs = _gear[{ f[0].GetUInt8(), f[1].GetUInt8() }];
                gs.gemRed = f[2].GetUInt32(); gs.gemYellow = f[3].GetUInt32(); gs.gemBlue = f[4].GetUInt32(); gs.gemMeta = f[5].GetUInt32();
            } while (r->NextRow());
        }
        uint32 pieces = 0;
        for (auto const& [k, gs] : _gear)
            pieces += gs.pieces.size();
        TC_LOG_INFO("npcbots", "BotArena gear: {} class/spec sets, {} pieces, {} distinct enchants", _gear.size(), pieces, _enchantNames.size());
        for (auto const& [id, name] : _enchantNames)
            TC_LOG_INFO("npcbots", "BotArena gear: enchant {} = {}", id, name);
        return pieces;
    }

    std::string GearText(uint8 cls, uint8 spec) const
    {
        auto itr = _gear.find({ cls, spec });
        if (itr == _gear.end())
            return "no gear set";
        std::ostringstream ss;
        for (auto const& [slot, gp] : itr->second.pieces)
        {
            ItemTemplate const* proto = sObjectMgr->GetItemTemplate(gp.item);
            ss << "  slot " << uint32(slot) << ": " << (proto ? proto->Name1 : "?") << " (" << gp.item << ")";
            if (gp.enchant)
            {
                auto en = _enchantNames.find(gp.enchant);
                ss << " +" << (en != _enchantNames.end() ? en->second : std::to_string(gp.enchant));
            }
            ss << "\n";
        }
        ss << "  gems: red " << itr->second.gemRed << " yellow " << itr->second.gemYellow << " blue " << itr->second.gemBlue << " meta " << itr->second.gemMeta << "\n";
        return ss.str();
    }

    // The gear hook: only answers while an arena team is being spawned.
    Item* GearFor(Creature* bot, uint8 cls, uint8 spec, uint8 slot)
    {
        if (!_spawningArena)
            return nullptr;
        auto itr = _gear.find({ cls, spec });
        if (itr == _gear.end())
            return nullptr;
        GearSet const& gs = itr->second;
        auto pit = gs.pieces.find(slot);
        if (pit == gs.pieces.end())
            return nullptr;
        uint32 itemId = pit->second.item;
        // faction-specific PvP trinket
        if (itemId == 51377 && bot && BotDataMgr::GetTeamIdForFaction(bot->GetFaction()) == TEAM_HORDE)
            itemId = 51378;
        ItemTemplate const* proto = sObjectMgr->GetItemTemplate(itemId);
        if (!proto)
            return nullptr;
        Item* item = Item::CreateItem(itemId, 1, nullptr);
        if (!item)
            return nullptr;
        auto setEnch = [item](uint8 eslot, uint32 id)
        {
            item->SetUInt32Value(ITEM_FIELD_ENCHANTMENT_1_1 + eslot * MAX_ENCHANTMENT_OFFSET + ENCHANTMENT_ID_OFFSET, id);
            item->SetUInt32Value(ITEM_FIELD_ENCHANTMENT_1_1 + eslot * MAX_ENCHANTMENT_OFFSET + ENCHANTMENT_DURATION_OFFSET, 0);
            item->SetUInt32Value(ITEM_FIELD_ENCHANTMENT_1_1 + eslot * MAX_ENCHANTMENT_OFFSET + ENCHANTMENT_CHARGES_OFFSET, 0);
        };
        if (pit->second.enchant)
            setEnch(uint8(PERM_ENCHANTMENT_SLOT), pit->second.enchant);
        bool allColorsMatched = true;
        bool anySocket = false;
        for (uint32 i = 0; i < MAX_ITEM_PROTO_SOCKETS; ++i)
        {
            uint32 color = proto->Socket[i].Color;
            if (!color)
                continue;
            anySocket = true;
            uint32 gem = 0;
            if (color & SOCKET_COLOR_META) gem = gs.gemMeta;
            else if (color & SOCKET_COLOR_RED) gem = gs.gemRed;
            else if (color & SOCKET_COLOR_YELLOW) gem = gs.gemYellow;
            else if (color & SOCKET_COLOR_BLUE) gem = gs.gemBlue;
            ItemTemplate const* gemProto = gem ? sObjectMgr->GetItemTemplate(gem) : nullptr;
            GemPropertiesEntry const* gp = gemProto ? sGemPropertiesStore.LookupEntry(gemProto->GemProperties) : nullptr;
            if (!gp)
            {
                allColorsMatched = false;
                continue;
            }
            setEnch(uint8(SOCK_ENCHANTMENT_SLOT) + uint8(i), gp->EnchantID);
        }
        if (anySocket && allColorsMatched && proto->socketBonus)
            setEnch(uint8(BONUS_ENCHANTMENT_SLOT), proto->socketBonus);
        ++_gearPiecesHanded;
        return item;
    }

    void ForgetSpectator(Player* player)
    {
        ClearViewpoint(player);
        std::erase_if(_spectators, [player](Spectator const& s) { return s.guid == player->GetGUID(); });
    }

    bool PreparePlayer(Player* player, uint32 buildId, std::string& err)
    {
        auto found = LobbyBuilds.find(buildId);
        if (!player || found == LobbyBuilds.end() || player->GetClass() != found->second.cls)
        { err = "invalid player or class/build mismatch"; return false; }
        if (player->InBattleground() || player->IsInCombat() || player->IsBeingTeleported())
        { err = "leave combat and the arena before changing build"; return false; }
        auto const& build = found->second;
        // Fresh death knights are confined to the phased starting map until Death Gate is known.
        if (build.cls == CLASS_DEATH_KNIGHT && player->GetMapId() == 609)
        {
            player->LearnSpell(50977, false);
            PlayerInfo const* start = sObjectMgr->GetPlayerInfo(RACE_HUMAN, CLASS_WARRIOR);
            player->TeleportTo(start->mapId, start->positionX, start->positionY, start->positionZ, 0);
            err = "character is teleporting to the lobby"; return false;
        }
        if (!_gear.contains({build.cls, build.spec})) LoadGear();
        if (!_gear.contains({build.cls, build.spec})) { err = "gear unavailable"; return false; }
        player->GiveLevel(80);
        player->ResetTalents(true);
        player->SetFreeTalentPoints(71);
        for (auto const& [talent, rank] : build.talents)
            if (!player->LearnTalent(talent, rank))
            { err = Trinity::StringFormat("invalid talent {} rank {}", talent, rank); return false; }
        // Class trainers validate race, class, prerequisites and required level.
        bool learned;
        do {
            learned = false;
            for (Trainer::Trainer const* trainer : sObjectMgr->GetClassTrainers(player->GetClass()))
                if (trainer->IsTrainerValidForPlayer(player))
                    for (Trainer::Spell const& spell : trainer->GetSpells())
                        if (trainer->CanTeachSpell(player, &spell))
                        {
                            if (spell.IsCastable()) player->CastSpell(player, spell.SpellId, true);
                            else player->LearnSpell(spell.SpellId, false);
                            learned = true;
                        }
        } while (learned);
        // Weapon/armour skills needed by these fixed templates (never bypass item class rules).
        static std::map<uint8,std::vector<uint32>> const proficiency = {
            {1,{196,197,198,199,200,201,202,203,204,227,264,266,2567,5011,9116,71,2458}},
            {2,{196,197,198,199,200,201,202,203,204,9116}},
            {3,{196,197,200,201,202,203,204,227,264,266,5011,1180,674,883,2641,1515,6991,982}},
            {4,{196,201,203,204,264,266,5011,1180,2567,674}}, {5,{198,203,204,227,1180,5009}},
            {6,{196,197,198,199,200,201,202,203,204,674}},
            {7,{196,197,198,199,203,204,227,1180,9116}}, {8,{201,203,204,227,1180,5009}},
            {9,{201,203,204,227,1180,5009,688,697,712,691}}, {11,{198,199,200,203,204,227,1180,5487,9634,768,783}}
        };
        for (uint32 spell : proficiency.at(build.cls)) player->LearnSpell(spell, false);
        if (build.cls == 1 || build.cls == 2 || build.cls == 6) player->LearnSpell(750, false);
        if (build.cls == 3 || build.cls == 7) player->LearnSpell(8737, false);
        if (build.cls == 4) player->LearnSpell(674, false);
        player->UpdateSkillsForLevel();
        player->UpdateWeaponsSkillsToMaxSkillsForLevel();
        static uint8 const slots[] = {EQUIPMENT_SLOT_MAINHAND,EQUIPMENT_SLOT_OFFHAND,EQUIPMENT_SLOT_RANGED,
            EQUIPMENT_SLOT_HEAD,EQUIPMENT_SLOT_SHOULDERS,EQUIPMENT_SLOT_CHEST,EQUIPMENT_SLOT_WAIST,
            EQUIPMENT_SLOT_LEGS,EQUIPMENT_SLOT_FEET,EQUIPMENT_SLOT_WRISTS,EQUIPMENT_SLOT_HANDS,
            EQUIPMENT_SLOT_BACK,EQUIPMENT_SLOT_BODY,EQUIPMENT_SLOT_FINGER1,EQUIPMENT_SLOT_FINGER2,
            EQUIPMENT_SLOT_TRINKET1,EQUIPMENT_SLOT_TRINKET2,EQUIPMENT_SLOT_NECK};
        for (uint8 slot = EQUIPMENT_SLOT_START; slot < EQUIPMENT_SLOT_END; ++slot)
            player->DestroyItem(INVENTORY_SLOT_BAG_0, slot, true);
        for (auto const& [slot, piece] : _gear.at({build.cls, build.spec}).pieces)
        {
            _spawningArena = true;
            Item* item = GearFor(nullptr, build.cls, build.spec, slot);
            _spawningArena = false;
            if (!item) { err = "could not create loadout item"; return false; }
            item->SetOwnerGUID(player->GetGUID());
            uint16 dest;
            auto result = player->CanEquipItem(slots[slot], dest, item, false);
            if (result != EQUIP_ERR_OK)
            { delete item; err = Trinity::StringFormat("cannot equip {}: {}", piece.item, uint32(result)); return false; }
            player->EquipItem(dest, item, true);
        }
        std::set<uint32> used;
        for (uint8 slot = 0; slot < MAX_GLYPH_SLOT_INDEX; ++slot)
        {
            if (auto old = sGlyphPropertiesStore.LookupEntry(player->GetGlyph(player->GetActiveTalentGroup(), slot)))
                player->RemoveAurasDueToSpell(old->SpellID);
            player->SetGlyph(slot, 0);
            auto type = sGlyphSlotStore.LookupEntry(player->GetGlyphSlot(slot));
            for (uint32 id : build.glyphs)
                if (auto glyph = sGlyphPropertiesStore.LookupEntry(id); glyph && type && glyph->GlyphSlotFlags == type->Type && !used.contains(id))
                { player->CastSpell(player, glyph->SpellID, true); player->SetGlyph(slot, id); used.insert(id); break; }
        }
        if (used.size() != 6) { err = "glyph slots not available"; return false; }
        if (build.cls == 3 && !player->GetPet())
            if (Pet* pet = player->CreateTamedPetFrom(705)) // wolf
            { pet->GetMap()->AddToMap(pet->ToCreature()); player->SetMinion(pet, true); pet->InitTalentForLevel(); pet->SavePetToDB(PET_SAVE_AS_CURRENT); player->PetSpellInitialize(); }
        if (build.cls == 3) { player->AddItem(52021, 2000); player->SetAmmo(52021); }
        if (build.cls == 9) player->AddItem(6265, 32);
        if (build.cls == 7) for (uint32 item : {5175u,5176u,5177u,5178u}) player->AddItem(item,1);
        player->SetFullHealth();
        player->SetPower(POWER_MANA, player->GetMaxPower(POWER_MANA));
        for (uint8 slot = 0; slot < 12; ++slot)
        {
            player->RemoveActionButton(slot);
            for (uint32 spell : build.actions[slot])
                if (player->HasSpell(spell)) { player->AddActionButton(slot, spell, ACTION_BUTTON_SPELL); break; }
        }
        player->SendInitialActionButtons();
        player->SendTalentsInfoData(false);
        player->SaveToDB();
        return true;
    }

    BrainParams& Brain() { return _brain; }
    BrainParams& BrainFor(uint32 team) { return _brainTeam[team == HORDE ? 1 : 0]; }
    void SyncBrains() { _brainTeam[0] = _brain; _brainTeam[1] = _brain; }

    std::string ParamsPath() const
    {
        return sConfigMgr->GetStringDefault("BotArena.BrainParams", "/conf/arenabrain.params");
    }

    std::string ResultsPath() const
    {
        return sConfigMgr->GetStringDefault("BotArena.ResultsFile", "/logs/botarena_matches.jsonl");
    }

    uint32 MaxConcurrent() const
    {
        return sConfigMgr->GetIntDefault("BotArena.MaxConcurrent", 16);
    }

    // Called from the bot cast hook (g_botCastHook) for every bot spell cast on the server.
    void RecordCast(Creature* bot, Unit* target, uint32 spellId)
    {
        for (auto& mp : _matches)
        {
            Match& m = *mp;
            if (m.state == State::Idle || m.bots.empty())
                continue;
            uint32 casterIdx = 0, targetIdx = 0;
            for (size_t i = 0; i < m.bots.size(); ++i)
            {
                if (m.bots[i].entry == bot->GetEntry())
                    casterIdx = uint32(i + 1);
                if (target && m.bots[i].guid == target->GetGUID())
                    targetIdx = uint32(i + 1);
            }
            if (!casterIdx)
                continue;
            if (Battleground const* bg = m.GetBG(); bg && bg->GetStatus() == STATUS_IN_PROGRESS)
                ++m.bots[casterIdx - 1].casts[spellId];
            m.events.push_back(CastEvent{ ++m.eventSeq, GameTime::GetGameTimeMS(), casterIdx, targetIdx, spellId });
            while (m.events.size() > 64)
                m.events.pop_front();
            return;
        }
    }

    // ---------------------------------------------------------------- match lifecycle
    Match* Start(uint8 arenaType, BattlegroundTypeId typeId, std::vector<ClassSpec> const& compA, std::vector<ClassSpec> const& compH,
        std::string const& compAStr, std::string const& compHStr, bool fromBatch, std::string& err, std::vector<Player*> const& humansA = {}, std::vector<Player*> const& humansH = {})
    {
        if (RunningCount() >= MaxConcurrent())
        {
            err = Trinity::StringFormat("too many concurrent matches ({}), raise BotArena.MaxConcurrent", MaxConcurrent());
            return nullptr;
        }
        if (compA.size() + humansA.size() != arenaType || compH.size() + humansH.size() != arenaType)
        {
            err = Trinity::StringFormat("comps must have exactly {} members each (got {} and {})", uint32(arenaType), compA.size(), compH.size());
            return nullptr;
        }
        if (typeId == BATTLEGROUND_AA)
            typeId = RandomArena();

        Battleground* bgTemplate = sBattlegroundMgr->GetBattlegroundTemplate(typeId);
        if (!bgTemplate)
        {
            err = "arena template not found";
            return nullptr;
        }
        uint32 mapId = bgTemplate->GetMapId();
        PvPDifficultyEntry const* bracket = GetBattlegroundBracketByLevel(mapId, sWorld->getIntConfig(CONFIG_MAX_PLAYER_LEVEL));
        if (!bracket)
        {
            err = "no pvp bracket for max level";
            return nullptr;
        }

        // Check both factions before allocating an instance or consuming any templates.
        for (uint32 team : { uint32(ALLIANCE), uint32(HORDE) })
        {
            std::map<uint8, uint32> needed;
            for (ClassSpec const& cs : team == ALLIANCE ? compA : compH)
                ++needed[cs.cls];
            for (auto const& [cls, count] : needed)
                if (uint32 available = BotDataMgr::GetArenaBotCapacity(cls, team, bracket->MaxLevel); available < count)
                {
                    err = Trinity::StringFormat("capacity: {} {} needs {}, available {}", team == ALLIANCE ? "A" : "H", ClassName(cls), count, available);
                    return nullptr;
                }
        }

        Battleground* bg = sBattlegroundMgr->CreateNewBattleground(typeId, bracket, arenaType, false);
        if (!bg)
        {
            err = "failed to create arena instance";
            return nullptr;
        }
        bg->SetBotArena(true);
        bg->StartBattleground();
        bg->RemoveFromBGFreeSlotQueue();

        Map* base = sMapMgr->CreateBaseMap(mapId);
        MapInstanced* mi = base ? base->ToMapInstanced() : nullptr;
        if (!mi)
        {
            bg->SetDeleteThis();
            err = "arena base map is not instanceable";
            return nullptr;
        }
        BattlegroundMap* bgMap = mi->CreateBattleground(bg->GetInstanceID(), bg);
        if (!bgMap)
        {
            bg->SetDeleteThis();
            err = "failed to create arena map";
            return nullptr;
        }

        auto mp = std::make_unique<Match>();
        Match& m = *mp;
        m.id = ++_nextMatchId;
        m.instanceId = bg->GetInstanceID();
        m.typeId = typeId;
        m.mapId = mapId;
        m.arenaType = arenaType;
        m.compAStr = compAStr;
        m.compHStr = compHStr;
        m.startedMs = GameTime::GetGameTimeMS();
        m.fromBatch = fromBatch;

        EnsureWanderNodes(bg, bgMap);

        if (!SpawnTeam(m, bg, bgMap, ALLIANCE, compA, err) || !SpawnTeam(m, bg, bgMap, HORDE, compH, err))
        {
            CleanupBots(m);
            bg->SetBotArena(false);
            bg->SetDeleteThis();
            return nullptr;
        }

        // Use the same invitation and world-port acknowledgement path as ordinary arenas.
        for (uint32 team : { uint32(ALLIANCE), uint32(HORDE) })
            for (Player* p : team == ALLIANCE ? humansA : humansH)
            {
                ForgetSpectator(p);
                p->SetGameMaster(false);
                p->SetGMVisible(true);
                p->RestoreDisplayId();
                p->SetBattlegroundEntryPoint();
                if (!p->IsAlive()) { p->ResurrectPlayer(1.0f); p->SpawnCorpseBones(); }
                p->SetFullHealth();
                p->SetBattlegroundId(bg->GetInstanceID(), bg->GetTypeID());
                p->SetBGTeam(team);
                auto queue = BattlegroundMgr::BGQueueTypeId(BATTLEGROUND_AA, bracket->GetBracketId(), arenaType);
                p->AddBattlegroundQueueId(queue);
                p->SetInviteForBattlegroundQueueType(queue, bg->GetInstanceID());
                bg->IncreaseInvitedCount(team);
                m.humans.push_back(p->GetGUID());
                sBattlegroundMgr->SendToBattleground(p, bg->GetInstanceID(), bg->GetTypeID());
            }

        m.state = State::Starting;
        TC_LOG_INFO("npcbots", "BotArena: match #{} started: {} {}v{} instance {} ({} vs {})", m.id, ArenaName(typeId), uint32(arenaType), uint32(arenaType), m.instanceId, compAStr, compHStr);
        _matches.push_back(std::move(mp));
        return _matches.back().get();
    }

    bool Stop(uint32 matchId, std::string& err)
    {
        bool any = false;
        for (auto& mp : _matches)
        {
            Match& m = *mp;
            if (matchId && m.id != matchId)
                continue;
            if (!m.Running())
                continue;
            any = true;
            if (Battleground* bg = m.GetBG())
                if (bg->GetStatus() < STATUS_WAIT_LEAVE)
                    bg->EndBattleground(0);
            if (!m.endRecorded)
            {
                m.endRecorded = true;
                m.durationMs = m.GetBG() ? m.GetBG()->GetElapsedTime() : 0;
            }
            m.state = State::Ended;
            m.endedAtMs = GameTime::GetGameTimeMS() - _leaveDelayMs + 2000; // cleanup in ~2s
        }
        if (!any)
        {
            err = matchId ? Trinity::StringFormat("no running match #{}", matchId) : "no bot arena match is active";
            return false;
        }
        return true;
    }

    void StopAll()
    {
        std::string err;
        _auto = false;
        _batch.active = false;
        Stop(0, err);
    }

    uint32 RunningCount() const
    {
        uint32 n = 0;
        for (auto const& mp : _matches)
            if (mp->Running())
                ++n;
        return n;
    }

    Match* FindMatch(uint32 id)
    {
        for (auto& mp : _matches)
            if (mp->id == id)
                return mp.get();
        return nullptr;
    }

    // The match spectators join by default: the oldest one still running (prefer one past preparation).
    Match* Featured()
    {
        Match* best = nullptr;
        for (auto& mp : _matches)
            if (mp->Running() && (!best || mp->id < best->id))
                best = mp.get();
        return best;
    }

    // ---------------------------------------------------------------- spectators
    bool Spectate(Player* player, uint32 matchId, std::string& err)
    {
        Match* m = matchId ? FindMatch(matchId) : Featured();
        if (!m || !m->Running())
        {
            err = matchId ? Trinity::StringFormat("match #{} is not running", matchId) : "no bot arena match is active";
            return false;
        }
        Battleground* bg = m->GetBG();
        BattlegroundMap* bgMap = bg ? bg->FindBgMap() : nullptr;
        if (!bgMap)
        {
            err = "arena map not created yet";
            return false;
        }
        Position c = Center(bg);
        float z = bgMap->GetHeight(c.GetPositionX(), c.GetPositionY(), c.GetPositionZ() + 10.0f, true, 50.0f);
        if (z <= INVALID_HEIGHT)
            z = c.GetPositionZ();

        if (!player->IsGameMaster())
            player->SetGameMaster(true);
        player->SetGMVisible(false);
        player->SetDisplayId(SPECTATOR_DISPLAY_ID);
        if (!player->InBattleground())
            player->SetBattlegroundEntryPoint();
        player->SetBattlegroundId(bg->GetInstanceID(), bg->GetTypeID());
        // Park the spectator high above the centre: the farsight camera does not depend on its position.
        if (!player->TeleportTo(m->mapId, c.GetPositionX(), c.GetPositionY(), z + 45.0f, c.GetOrientation()))
        {
            err = "teleport failed";
            return false;
        }
        Spectator& s = SpectatorFor(player->GetGUID());
        s.matchId = m->id;
        s.initialViewPending = true;
        s.lastSentSeq = 0;
        s.rejoinAtMs = 0;
        return true;
    }

    bool Camera(Player* player, std::string const& target, std::string& err)
    {
        std::string t = Lower(target);
        Spectator& s = SpectatorFor(player->GetGUID());
        if (t == "off" || t == "free" || t == "self")
        {
            ClearViewpoint(player);
            s.camAuto = false;
            s.initialViewPending = false;
            return true;
        }
        if (t == "auto")
        {
            s.camAuto = true;
            s.camLastMs = 0;
            return true;
        }
        s.camAuto = false;
        Match* m = FindMatch(s.matchId);
        if (!m)
        {
            err = "you are not spectating a match (.botarena spectate)";
            return false;
        }
        ArenaBot const* ab = FindBot(*m, t);
        if (!ab)
        {
            err = "bot not found: " + target;
            return false;
        }
        bool ok = SetCamera(player, *ab, err);
        if (ok) s.initialViewPending = false;
        return ok;
    }

    // ---------------------------------------------------------------- auto rotation & batch
    void SetAuto(bool on, uint32 delaySeconds)
    {
        _auto = on;
        if (delaySeconds)
            _autoDelayMs = delaySeconds * IN_MILLISECONDS;
        _autoTimerMs = 0;
    }
    bool IsAuto() const { return _auto; }

    bool StartBatch(uint32 total, uint32 concurrency, uint8 type, BattlegroundTypeId arena, std::string const& compA, std::string const& compH, std::string& err)
    {
        if (_batch.active)
        {
            err = Trinity::StringFormat("a batch is already running ({}/{} done); '.botarena batch stop' first", _batch.done, _batch.total);
            return false;
        }
        _batch = Batch{};
        _batch.active = true;
        _batch.total = total;
        _batch.concurrency = std::max<uint32>(1, std::min<uint32>(concurrency, MaxConcurrent()));
        _batch.type = type;
        _batch.arena = arena;
        _batch.compA = compA;
        _batch.compH = compH;
        _batch.startedAtMs = GameTime::GetGameTimeMS();
        TC_LOG_INFO("npcbots", "BotArena: batch started: {} matches, concurrency {}, {}v{}, {} vs {}", total, _batch.concurrency, uint32(type), uint32(type), compA, compH);
        return true;
    }

    void StopBatch() { _batch.active = false; }
    Batch const& GetBatch() const { return _batch; }

    // ---------------------------------------------------------------- update
    void Update(uint32 diff)
    {
        for (auto& mp : _matches)
            UpdateMatch(*mp, diff);

        // drop finished matches once their battleground is gone (keep the last few for status)
        for (auto itr = _matches.begin(); itr != _matches.end();)
        {
            Match& m = **itr;
            if (m.state == State::Idle && m.logged)
            {
                _recent.push_front(m.resultLine);
                while (_recent.size() > 10)
                    _recent.pop_back();
                itr = _matches.erase(itr);
            }
            else
                ++itr;
        }

        UpdateBatch(diff);
        if (_auto && !_batch.active)
            UpdateAuto(diff);

        _feedTimer += diff;
        if (_feedTimer >= 500)
        {
            _feedTimer = 0;
            SendFeeds();
        }
        _camTimer += diff;
        if (_camTimer >= 1000)
        {
            _camTimer = 0;
            UpdateAutoCameras();
            UpdateRejoins();
        }
    }

    // ---------------------------------------------------------------- status
    std::string StatusText()
    {
        std::ostringstream ss;
        ss << "BotArena: " << RunningCount() << " running match(es), auto " << (_auto ? "on" : "off")
           << ", batch " << (_batch.active ? Trinity::StringFormat("{}/{} done (A {} H {} draw {}), concurrency {}", _batch.done, _batch.total, _batch.winsA, _batch.winsH, _batch.draws, _batch.concurrency) : std::string("off")) << "\n";
        for (std::string const& r : _recent)
            ss << "recent: " << r << "\n";
        for (auto& mp : _matches)
        {
            Match& m = *mp;
            Battleground const* bg = m.GetBG();
            ss << "match #" << m.id << " " << StateName(m.state) << " " << ArenaName(m.typeId) << " " << uint32(m.arenaType) << "v" << uint32(m.arenaType)
               << " instance " << m.instanceId << " bgstatus " << (bg ? uint32(bg->GetStatus()) : 0)
               << " elapsed " << (bg ? bg->GetElapsedTime() / IN_MILLISECONDS : 0) << "s winner " << WinnerName(m.winner)
               << " [" << m.compAStr << " vs " << m.compHStr << "]\n";
            uint32 i = 0;
            for (ArenaBot const& ab : m.bots)
            {
                ++i;
                Creature const* bot = BotDataMgr::FindBot(ab.entry);
                ss << "  " << i << ". [" << (ab.team == ALLIANCE ? "A" : "H") << "] " << (bot ? bot->GetName() : ab.name)
                   << " " << ClassName(ab.cs.cls) << "/" << SpecName(ab.cs.spec);
                if (bot)
                    ss << " hp " << uint32(bot->GetHealthPct()) << "% " << (bot->IsAlive() ? "alive" : "dead")
                       << (bot->GetVictim() ? " -> " + bot->GetVictim()->GetName() : "")
                       << (bot->HasAuraType(SPELL_AURA_MOD_STEALTH) ? " (stealth)" : "")
                       << (ab.kiteUntilMs ? " (kiting)" : "");
                else
                    ss << " (not spawned)";
                ss << "\n";
            }
            for (int t = 0; t < 2; ++t)
                if (!m.killTarget[t].IsEmpty())
                    for (ArenaBot const& ab : m.bots)
                        if (ab.guid == m.killTarget[t])
                            ss << "  kill target " << (t == 0 ? "A" : "H") << ": " << ab.name << "\n";
        }
        for (Spectator const& s : _spectators)
            if (Player const* p = ObjectAccessor::FindConnectedPlayer(s.guid))
                ss << "spectator " << p->GetName() << " match #" << s.matchId << " map " << p->GetMapId() << " view: "
                   << (p->GetViewpoint() ? p->GetViewpoint()->GetName() : std::string("self")) << (s.camAuto ? " (auto)" : "") << "\n";
        ss << "brain: " << _brain.Show() << "\n";
        return ss.str();
    }

    static void WriteBotTelemetry(std::ostream& ss, ArenaBot const& ab, Creature const* bot)
    {
        bot_ai const* ai = bot ? bot->GetBotAI() : nullptr;
        ss << ",\"actualSpec\":" << Json(ai ? SpecName(ai->GetSpec()) : "unknown")
           << ",\"roles\":" << (ai ? ai->GetBotRoles() : 0)
           << ",\"setupVerified\":" << (ab.setupVerified ? "true" : "false")
           << ",\"mana\":" << (bot ? bot->GetPower(POWER_MANA) : 0)
           << ",\"maxMana\":" << (bot ? bot->GetMaxPower(POWER_MANA) : 0)
           << ",\"moving\":" << (bot && bot->isMoving() ? "true" : "false")
           << ",\"casting\":" << (bot && bot->IsNonMeleeSpellCast(false) ? "true" : "false")
           << ",\"cc\":" << (bot && bot->HasUnitState(UNIT_STATE_CONTROLLED) ? "true" : "false")
           << ",\"equipment\":[";
        for (uint8 slot = 0; slot < BOT_INVENTORY_SIZE; ++slot)
        {
            if (slot) ss << ",";
            Item const* item = ai ? ai->GetEquips(slot) : nullptr;
            ss << (item ? item->GetEntry() : 0);
        }
        ss << "],\"casts\":{";
        bool first = true;
        for (auto const& [spell, count] : ab.casts)
        {
            if (!first) ss << ",";
            first = false;
            ss << Json(std::to_string(spell)) << ":" << count;
        }
        ss << "}";
    }

    std::string StatusJson()
    {
        std::ostringstream ss;
        ss << "{\"running\":" << RunningCount()
           << ",\"auto\":" << (_auto ? "true" : "false")
           << ",\"batch\":{\"active\":" << (_batch.active ? "true" : "false") << ",\"total\":" << _batch.total << ",\"done\":" << _batch.done
           << ",\"started\":" << _batch.started << ",\"winsA\":" << _batch.winsA << ",\"winsH\":" << _batch.winsH << ",\"draws\":" << _batch.draws
           << ",\"concurrency\":" << _batch.concurrency << "}"
           << ",\"matches\":[";
        bool first = true;
        for (auto& mp : _matches)
        {
            Match& m = *mp;
            Battleground const* bg = m.GetBG();
            if (!first) ss << ",";
            first = false;
            ss << "{\"id\":" << m.id << ",\"state\":" << Json(StateName(m.state)) << ",\"arena\":" << Json(ArenaName(m.typeId))
               << ",\"mapId\":" << m.mapId << ",\"type\":" << uint32(m.arenaType) << ",\"instance\":" << m.instanceId
               << ",\"bgStatus\":" << (bg ? uint32(bg->GetStatus()) : 0) << ",\"elapsed\":" << (bg ? bg->GetElapsedTime() / IN_MILLISECONDS : 0)
               << ",\"winner\":" << Json(WinnerName(m.winner)) << ",\"compA\":" << Json(m.compAStr) << ",\"compH\":" << Json(m.compHStr) << ",\"bots\":[";
            uint32 i = 0;
            bool fb = true;
            for (ArenaBot const& ab : m.bots)
            {
                ++i;
                Creature const* bot = BotDataMgr::FindBot(ab.entry);
                if (!fb) ss << ",";
                fb = false;
                ss << "{\"idx\":" << i << ",\"team\":" << Json(ab.team == ALLIANCE ? "A" : "H") << ",\"name\":" << Json(bot ? bot->GetName() : ab.name)
                   << ",\"class\":" << Json(ClassName(ab.cs.cls)) << ",\"spec\":" << Json(SpecName(ab.cs.spec))
                   << ",\"hp\":" << (bot ? bot->GetHealth() : 0) << ",\"maxhp\":" << (bot ? bot->GetMaxHealth() : 0)
                   << ",\"alive\":" << (bot && bot->IsAlive() ? "true" : "false")
                   << ",\"target\":" << Json(bot && bot->GetVictim() ? bot->GetVictim()->GetName() : "");
                Position const* start = bg ? bg->GetTeamStartPosition(ab.team == ALLIANCE ? TEAM_ALLIANCE : TEAM_HORDE) : nullptr;
                ss << ",\"startDistance\":" << (bot && start ? bot->GetExactDist(start) : -1.0f);
                WriteBotTelemetry(ss, ab, bot);
                ss << "}";
            }
            ss << "],\"humans\":[";
            bool firstHuman = true;
            for (ObjectGuid guid : m.humans)
            {
                Player* p = ObjectAccessor::FindConnectedPlayer(guid);
                if (!firstHuman) ss << ",";
                firstHuman = false;
                ss << "{\"name\":" << Json(p ? p->GetName() : "offline")
                   << ",\"team\":" << Json(p && p->GetBGTeam() == ALLIANCE ? "A" : "H")
                   << ",\"joined\":" << (bg && bg->IsPlayerInBattleground(guid) ? "true" : "false") << "}";
            }
            ss << "]}";
        }
        ss << "],\"capacity\":{";
        bool firstCapacity = true;
        for (uint32 team : { uint32(ALLIANCE), uint32(HORDE) })
            for (uint8 cls : { 1, 2, 3, 4, 5, 6, 7, 8, 9, 11 })
            {
                if (!firstCapacity) ss << ",";
                firstCapacity = false;
                ss << Json(std::string(team == ALLIANCE ? "A:" : "H:") + ClassName(cls)) << ":"
                   << BotDataMgr::GetArenaBotCapacity(cls, team, sWorld->getIntConfig(CONFIG_MAX_PLAYER_LEVEL));
            }
        ss << "},\"recent\":[";
        first = true;
        for (std::string const& r : _recent)
        {
            if (!first) ss << ",";
            first = false;
            ss << Json(r);
        }
        ss << "],\"spectators\":" << _spectators.size() << ",\"brain\":" << Json(_brain.Show()) << "}";
        return ss.str();
    }

    // For the HUD: the status line of the match a spectator watches (compatible with the addon's S line).
    // --------------------------------------------------------------------------------------------
private:
    BotArenaMgr()
    {
        _brain.LoadFile(ParamsPath());
        SyncBrains();
    }
    std::map<std::pair<uint8, uint8>, GearSet> _gear;
    std::map<uint32, std::string> _enchantNames;
    bool _spawningArena = false;
    uint32 _gearPiecesHanded = 0;

    static char const* StateName(State s)
    {
        switch (s)
        {
            case State::Idle: return "idle";
            case State::Starting: return "starting";
            case State::Running: return "running";
            case State::Ended: return "ended";
        }
        return "?";
    }

    static char const* WinnerName(PvPTeamId w)
    {
        switch (w)
        {
            case PVP_TEAM_ALLIANCE: return "A";
            case PVP_TEAM_HORDE: return "H";
            default: return "none";
        }
    }

    Spectator& SpectatorFor(ObjectGuid guid)
    {
        for (Spectator& s : _spectators)
            if (s.guid == guid)
                return s;
        _spectators.push_back(Spectator{ guid });
        return _spectators.back();
    }

    Position Center(Battleground const* bg) const
    {
        Position const* a = bg->GetTeamStartPosition(TEAM_ALLIANCE);
        Position const* h = bg->GetTeamStartPosition(TEAM_HORDE);
        if (!a || !h)
            return Position();
        float x = (a->GetPositionX() + h->GetPositionX()) / 2.0f;
        float y = (a->GetPositionY() + h->GetPositionY()) / 2.0f;
        float z = (a->GetPositionZ() + h->GetPositionZ()) / 2.0f;
        float o = a->GetAbsoluteAngle(h);
        return Position(x, y, z, o);
    }

    static uint32 FallbackZone(uint32 mapId)
    {
        switch (mapId)
        {
            case 559: return 3698;
            case 562: return 3702;
            case 572: return 3968;
            case 617: return 4378;
            case 618: return 4406;
            default: return 0;
        }
    }

    void EnsureWanderNodes(Battleground const* bg, BattlegroundMap* bgMap)
    {
        uint32 mapId = bg->GetMapId();
        if (WanderNode::FindInMapWPs(mapId, [](WanderNode const* wp) { return wp->HasFlag(BotWPFlags::BOTWP_FLAG_SPAWN); }))
            return;

        Position const* a = bg->GetTeamStartPosition(TEAM_ALLIANCE);
        Position const* h = bg->GetTeamStartPosition(TEAM_HORDE);
        if (!a || !h)
            return;

        uint32 zone = 0, area = 0;
        bgMap->GetZoneAndAreaId(PHASEMASK_NORMAL, zone, area, *a);
        if (!zone || !sAreaTableStore.LookupEntry(zone))
            zone = FallbackZone(mapId);
        if (!area || !sAreaTableStore.LookupEntry(area))
            area = zone;
        if (!zone)
        {
            TC_LOG_ERROR("npcbots", "BotArena: cannot determine zone for map {}", mapId);
            return;
        }

        auto fixZ = [bgMap](float x, float y, float z)
        {
            float gz = bgMap->GetHeight(x, y, z + 5.0f, true, 30.0f);
            return gz > INVALID_HEIGHT ? gz + 0.5f : z;
        };
        auto mk = [&](std::string name, float x, float y, float z, float o, BotWPFlags flags)
        {
            if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z))
            {
                z = a->GetPositionZ();
                if (!std::isfinite(x) || !std::isfinite(y)) { x = a->GetPositionX(); y = a->GetPositionY(); }
            }
            WanderNode* wp = new WanderNode(++WanderNode::nextWPId, mapId, x, y, z, o, zone, area, std::move(name));
            wp->SetLevels(1, DEFAULT_MAX_LEVEL);
            wp->SetFlags(flags);
            return wp;
        };

        Position c = Center(bg);
        float dx = h->GetPositionX() - a->GetPositionX();
        float dy = h->GetPositionY() - a->GetPositionY();
        float len = std::sqrt(dx * dx + dy * dy);
        if (len < 1.0f) len = 1.0f;
        float px = -dy / len, py = dx / len;
        float off = std::min(12.0f, len / 4.0f);

        WanderNode* spawnA = mk("ArenaSpawnA", a->GetPositionX(), a->GetPositionY(), a->GetPositionZ(), a->GetOrientation(),
            BotWPFlags::BOTWP_FLAG_SPAWN | BotWPFlags::BOTWP_FLAG_ALLIANCE_ONLY | BotWPFlags::BOTWP_FLAG_CAN_BACKTRACK_FROM);
        WanderNode* spawnH = mk("ArenaSpawnH", h->GetPositionX(), h->GetPositionY(), h->GetPositionZ(), h->GetOrientation(),
            BotWPFlags::BOTWP_FLAG_SPAWN | BotWPFlags::BOTWP_FLAG_HORDE_ONLY | BotWPFlags::BOTWP_FLAG_CAN_BACKTRACK_FROM);
        WanderNode* center = mk("ArenaCenter", c.GetPositionX(), c.GetPositionY(), fixZ(c.GetPositionX(), c.GetPositionY(), c.GetPositionZ()), c.GetOrientation(), BotWPFlags::BOTWP_FLAG_CAN_BACKTRACK_FROM);
        WanderNode* side1 = mk("ArenaSide1", c.GetPositionX() + px * off, c.GetPositionY() + py * off, fixZ(c.GetPositionX() + px * off, c.GetPositionY() + py * off, c.GetPositionZ()), c.GetOrientation(), BotWPFlags::BOTWP_FLAG_CAN_BACKTRACK_FROM);
        WanderNode* side2 = mk("ArenaSide2", c.GetPositionX() - px * off, c.GetPositionY() - py * off, fixZ(c.GetPositionX() - px * off, c.GetPositionY() - py * off, c.GetPositionZ()), c.GetOrientation(), BotWPFlags::BOTWP_FLAG_CAN_BACKTRACK_FROM);
        float qx = (a->GetPositionX() + c.GetPositionX()) / 2.0f, qy = (a->GetPositionY() + c.GetPositionY()) / 2.0f;
        WanderNode* midA = mk("ArenaMidA", qx, qy, fixZ(qx, qy, a->GetPositionZ()), c.GetOrientation(), BotWPFlags::BOTWP_FLAG_CAN_BACKTRACK_FROM);
        float rx = (h->GetPositionX() + c.GetPositionX()) / 2.0f, ry = (h->GetPositionY() + c.GetPositionY()) / 2.0f;
        WanderNode* midH = mk("ArenaMidH", rx, ry, fixZ(rx, ry, h->GetPositionZ()), c.GetOrientation(), BotWPFlags::BOTWP_FLAG_CAN_BACKTRACK_FROM);

        auto link = [](WanderNode* x, WanderNode* y)
        {
            x->Link(WanderNode::WanderNodeLink{ .wp = y, .weight = 1 });
            y->Link(WanderNode::WanderNodeLink{ .wp = x, .weight = 1 });
        };
        link(spawnA, midA); link(midA, center); link(midA, side1); link(midA, side2);
        link(center, side1); link(center, side2); link(center, midH);
        link(midH, side1); link(midH, side2); link(midH, spawnH);
        TC_LOG_INFO("npcbots", "BotArena: created 7 wander nodes for map {}", mapId);
    }

    bool SpawnTeam(Match& m, Battleground* bg, BattlegroundMap* bgMap, uint32 team, std::vector<ClassSpec> const& comp, std::string& err)
    {
        std::vector<std::pair<uint8, uint8>> classSpecs;
        for (ClassSpec const& cs : comp)
            classSpecs.emplace_back(cs.cls, cs.spec);

        PvPDifficultyEntry const* bracket = GetBattlegroundBracketByLevel(bg->GetMapId(), sWorld->getIntConfig(CONFIG_MAX_PLAYER_LEVEL));
        NpcBotRegistry registry;
        _spawningArena = true;
        uint32 handedBefore = _gearPiecesHanded;
        bool generated = BotDataMgr::GenerateArenaBots(classSpecs, bg->GetMapId(), team, bracket, &registry);
        _spawningArena = false;
        TC_LOG_INFO("npcbots", "BotArena gear: handed {} set pieces to team {} of match", _gearPiecesHanded - handedBefore, team == ALLIANCE ? "A" : "H");
        if (!generated)
        {
            err = Trinity::StringFormat("failed to generate {} bots for team {} (not enough spare bots of the requested classes/faction?)", comp.size(), team == ALLIANCE ? "A" : "H");
            for (Creature const* bot : registry)
                BotDataMgr::DespawnWandererBot(bot->GetEntry());
            return false;
        }

        std::vector<ClassSpec> remaining = comp;
        TeamId teamId = team == ALLIANCE ? TEAM_ALLIANCE : TEAM_HORDE;
        Position const* start = bg->GetTeamStartPosition(teamId);
        for (Creature const* cbot : registry)
        {
            Creature* bot = const_cast<Creature*>(cbot);
            ArenaBot ab;
            ab.entry = bot->GetEntry();
            ab.guid = bot->GetGUID();
            ab.team = team;
            ab.name = bot->GetName();
            ab.cs.cls = bot->GetBotAI() ? bot->GetBotAI()->GetBotClass() : 0;
            ab.cs.spec = bot->GetBotAI() ? bot->GetBotAI()->GetSpec() : 0;
            auto it = std::find_if(remaining.begin(), remaining.end(), [&](ClassSpec const& cs) { return cs.cls == ab.cs.cls && cs.spec == ab.cs.spec; });
            if (it == remaining.end())
            {
                err = "generated bot class/spec does not match requested lineup";
                for (Creature const* generatedBot : registry)
                    BotDataMgr::DespawnWandererBot(generatedBot->GetEntry());
                return false;
            }
            if (it != remaining.end())
            {
                ab.cs = *it;
                remaining.erase(it);
            }
            m.bots.push_back(ab);
            if (bot_ai* ai = bot->GetBotAI())
            {
                ai->SetBotCommandState(BOT_COMMAND_STAY);
                ai->SetBG(bg);
            }
            bot->SetPvP(true);
            if (start)
                BotMgr::TeleportBot(bot, bgMap, start, true, false);
        }
        return true;
    }

    void CleanupBots(Match& m)
    {
        // Every spectator of this match must drop its viewpoint before a bot is deleted (~Unit asserts m_sharedVision is empty).
        for (Spectator& s : _spectators)
            if (s.matchId == m.id)
                if (Player* p = ObjectAccessor::FindConnectedPlayer(s.guid))
                    ClearViewpoint(p);
        for (ArenaBot const& ab : m.bots)
            if (Creature const* bot = BotDataMgr::FindBot(ab.entry))
            {
                if (bot->GetBotAI())
                    bot->GetBotAI()->SetArenaTarget(ObjectGuid::Empty);
                if (bot->IsWandererBot())
                    BotDataMgr::DespawnWandererBot(ab.entry);
            }
        m.bots.clear();
    }

    ArenaBot const* FindBot(Match& m, std::string const& t) const
    {
        if (Optional<uint32> idx = Trinity::StringTo<uint32>(t))
            if (*idx >= 1 && *idx <= m.bots.size())
                return &m.bots[*idx - 1];
        for (ArenaBot const& ab : m.bots)
            if (Lower(ab.name) == t)
                return &ab;
        return nullptr;
    }

    static void ClearViewpoint(Player* player)
    {
        if (WorldObject* cur = player->GetViewpoint())
            player->SetViewpoint(cur, false);
    }

    bool SetCamera(Player* player, ArenaBot const& ab, std::string& err)
    {
        Creature const* cbot = BotDataMgr::FindBot(ab.entry);
        if (!cbot || !cbot->IsInWorld())
        {
            err = "bot is not in world";
            return false;
        }
        if (player->GetMap() != cbot->GetMap())
        {
            err = "you must be spectating in the arena (.botarena spectate)";
            return false;
        }
        Creature* bot = const_cast<Creature*>(cbot);
        if (player->GetViewpoint() == bot)
            return true;
        ClearViewpoint(player);
        player->SetViewpoint(bot, true);
        return true;
    }

    // ---------------------------------------------------------------- per match update
    void UpdateMatch(Match& m, uint32 diff)
    {
        if (m.state == State::Idle)
            return;

        Battleground* bg = m.GetBG();
        if (!bg)
        {
            // Battleground object was deleted: the match is over.
            CleanupBots(m);
            if (!m.logged)
                LogResult(m, nullptr);
            m.resultLine = Trinity::StringFormat("match {} on {}: winner {} after {}s ({} vs {})", m.id, ArenaName(m.typeId), WinnerName(m.winner), m.durationMs / IN_MILLISECONDS, m.compAStr, m.compHStr);
            TC_LOG_INFO("npcbots", "BotArena: {}", m.resultLine);
            if (m.fromBatch)
            {
                ++_batch.done;
                if (m.winner == PVP_TEAM_ALLIANCE) ++_batch.winsA; else if (m.winner == PVP_TEAM_HORDE) ++_batch.winsH; else ++_batch.draws;
            }
            m.state = State::Idle;
            _autoTimerMs = 0;
            return;
        }

        BattlegroundMap* bgMap = bg->FindBgMap();

        if (m.state == State::Starting)
        {
            bool allAdded = true;
            if (!m.humans.empty() && GameTime::GetGameTimeMS() - m.startedMs > 90000)
            { std::string ignored; Stop(m.id, ignored); return; }
            for (ObjectGuid guid : m.humans)
                if (!bg->IsPlayerInBattleground(guid))
                    allAdded = false;
            for (ArenaBot& ab : m.bots)
            {
                if (ab.added)
                    continue;
                Creature const* cbot = BotDataMgr::FindBot(ab.entry);
                if (!cbot || !bgMap)
                {
                    allAdded = false;
                    continue;
                }
                Creature* bot = const_cast<Creature*>(cbot);
                bot_ai* ai = bot->GetBotAI();
                if (!bot->IsInWorld() || bot->FindMap() != bgMap || !ai || ai->IsDuringTeleport())
                {
                    allAdded = false;
                    continue;
                }
                ab.guid = bot->GetGUID();
                ab.name = bot->GetName();
                if (!bg->GetBots().contains(ab.guid))
                {
                    ai->SetBG(bg);
                    bg->IncreaseInvitedCount(ab.team);
                    bg->AddBot(bot);
                }
                ai->SetBotCommandState(BOT_COMMAND_STAY);
                bot->SetPvP(true);
                // Never repair a spec after equipment/roles have initialized: reject a bad setup.
                bool valid = ai->GetSpec() == ab.cs.spec &&
                    ai->GetBotRoles() == BotDataMgr::ArenaRolesForSpec(ab.cs.cls, ab.cs.spec);
                auto gear = _gear.find({ ab.cs.cls, ab.cs.spec });
                valid = valid && gear != _gear.end();
                if (gear != _gear.end())
                    for (auto const& [slot, piece] : gear->second.pieces)
                    {
                        uint32 expected = piece.item == 51377 && ab.team == HORDE ? 51378 : piece.item;
                        if (expected && (!ai->GetEquips(slot) || ai->GetEquips(slot)->GetEntry() != expected))
                            valid = false;
                    }
                if (!valid)
                {
                    TC_LOG_ERROR("npcbots", "BotArena: setup verification failed for {} class {} spec {} roles {}", ab.name, uint32(ab.cs.cls), uint32(ai->GetSpec()), ai->GetBotRoles());
                    m.state = State::Running; // leave Starting so the failure is logged once
                    bg->EndBattleground(0);
                    return;
                }
                ab.setupVerified = true;
                bot->CastSpell(bot, ab.team == ALLIANCE ? ARENA_FLAG_TEAM_A_GOLD : ARENA_FLAG_TEAM_H_GREEN, true);
                if (Position const* start = bg->GetTeamStartPosition(ab.team == ALLIANCE ? TEAM_ALLIANCE : TEAM_HORDE))
                    if (bot->GetExactDist(start) > 1.0f)
                    {
                        BotMgr::TeleportBot(bot, bgMap, start, true, false);
                        allAdded = false;
                        continue;
                    }
                ab.added = true;
            }
            if (allAdded)
                m.state = State::Running;
        }

        if (m.state == State::Running)
        {
            m.brainTimer += diff;
            if (m.brainTimer >= _brain.tickMs)
            {
                m.brainTimer = 0;
                BrainTick(m, bg, bgMap);
            }
        }

        if (m.state == State::Running && bg->GetStatus() == STATUS_IN_PROGRESS)
        {
            // Make sure no bot stays in STAY mode once the gates are open (unless it is a deliberate kite step).
            uint32 now = GameTime::GetGameTimeMS();
            for (ArenaBot& ab : m.bots)
                if (Creature const* bot = BotDataMgr::FindBot(ab.entry))
                    if (bot_ai* ai = bot->GetBotAI())
                    {
                        if (ab.kiteUntilMs && now >= ab.kiteUntilMs)
                            ab.kiteUntilMs = 0;
                        if (!ab.kiteUntilMs && ai->HasBotCommandState(BOT_COMMAND_STAY))
                            ai->RemoveBotCommandState(BOT_COMMAND_STAY);
                    }

            uint32 aliveA = bg->GetAlivePlayersCountByTeam(ALLIANCE);
            uint32 aliveH = bg->GetAlivePlayersCountByTeam(HORDE);
            if (!aliveA && !aliveH)
                bg->EndBattleground(0);
            else if (!aliveA)
                bg->EndBattleground(HORDE);
            else if (!aliveH)
                bg->EndBattleground(ALLIANCE);
            else if (_maxDurationMs && bg->GetElapsedTime() >= _maxDurationMs)
                bg->EndBattleground(0);
        }

        if (bg->GetStatus() == STATUS_WAIT_LEAVE && !m.endRecorded)
        {
            m.endRecorded = true;
            m.winner = bg->GetWinner();
            m.durationMs = bg->GetElapsedTime();
            m.state = State::Ended;
            m.endedAtMs = GameTime::GetGameTimeMS();
            LogResult(m, bg);
            TC_LOG_INFO("npcbots", "BotArena: match #{} ended: winner {}", m.id, WinnerName(m.winner));
            for (Spectator& s : _spectators)
                if (s.matchId == m.id)
                    if (Player* p = ObjectAccessor::FindConnectedPlayer(s.guid))
                        ClearViewpoint(p);
        }

        if (m.state == State::Ended && GameTime::GetGameTimeMS() - m.endedAtMs >= _leaveDelayMs)
        {
            std::vector<ObjectGuid> guids;
            for (auto const& [guid, _] : bg->GetBots())
                guids.push_back(guid);
            for (ObjectGuid guid : guids)
                bg->RemoveBotAtLeave(guid);
            CleanupBots(m);
            if (bg->GetBots().empty() && bg->GetPlayers().empty())
                bg->SetDeleteThis();
        }
    }

    // Append one JSON line per finished match (the headless farm's dataset).
    void LogResult(Match& m, Battleground const* bg)
    {
        m.logged = true;
        std::ostringstream ss;
        bool valid = m.durationMs >= 60 * IN_MILLISECONDS && !m.bots.empty() &&
            bg && std::all_of(m.bots.begin(), m.bots.end(), [bg](ArenaBot const& b) {
                auto score = bg->GetBotScores().find(b.guid);
                return b.setupVerified && score != bg->GetBotScores().end() && score->second;
            });
        ss << "{\"schema\":2,\"valid\":" << (valid ? "true" : "false") << ",\"match\":" << m.id << ",\"time\":" << GameTime::GetGameTime() << ",\"arena\":" << Json(ArenaName(m.typeId)) << ",\"mapId\":" << m.mapId
           << ",\"type\":" << uint32(m.arenaType) << ",\"winner\":" << Json(WinnerName(m.winner)) << ",\"duration\":" << m.durationMs / IN_MILLISECONDS
           << ",\"compA\":" << Json(m.compAStr) << ",\"compH\":" << Json(m.compHStr) << ",\"batch\":" << (m.fromBatch ? "true" : "false")
           << ",\"brainA\":" << Json(_brainTeam[0].Show()) << ",\"brainH\":" << Json(_brainTeam[1].Show()) << ",\"bots\":[";
        bool first = true;
        for (ArenaBot const& ab : m.bots)
        {
            Creature const* bot = BotDataMgr::FindBot(ab.entry);
            uint32 dmg = 0, heal = 0, kb = 0, deaths = 0;
            if (bg)
            {
                auto itr = bg->GetBotScores().find(ab.guid);
                if (itr != bg->GetBotScores().end() && itr->second)
                {
                    dmg = itr->second->GetDamageDone();
                    heal = itr->second->GetHealingDone();
                    kb = itr->second->GetKillingBlows();
                    deaths = itr->second->GetDeaths();
                }
            }
            if (!first) ss << ",";
            first = false;
            ss << "{\"team\":" << Json(ab.team == ALLIANCE ? "A" : "H") << ",\"name\":" << Json(ab.name) << ",\"class\":" << Json(ClassName(ab.cs.cls))
               << ",\"spec\":" << Json(SpecName(ab.cs.spec)) << ",\"damage\":" << dmg << ",\"healing\":" << heal << ",\"killingBlows\":" << kb
               << ",\"deaths\":" << deaths << ",\"alive\":" << (bot && bot->IsAlive() ? "true" : "false")
               << ",\"hp\":" << (bot ? uint32(bot->GetHealthPct()) : 0);
            WriteBotTelemetry(ss, ab, bot);
            ss << "}";
        }
        ss << "]}";
        std::ofstream out(ResultsPath(), std::ios::app);
        if (out)
            out << ss.str() << "\n";
        else
            TC_LOG_ERROR("npcbots", "BotArena: cannot write results to {}", ResultsPath());
    }

    // ---------------------------------------------------------------- ArenaBrain v1
    static bool IsCrowdControlled(Unit const* u)
    {
        return u->HasAuraType(SPELL_AURA_MOD_STUN) || u->HasAuraType(SPELL_AURA_MOD_FEAR) || u->HasAuraType(SPELL_AURA_MOD_CONFUSE)
            || u->HasAuraType(SPELL_AURA_TRANSFORM) || u->HasAuraType(SPELL_AURA_MOD_PACIFY_SILENCE) || u->HasAuraType(SPELL_AURA_MOD_PACIFY);
    }

    static bool IsHealer(bot_ai const* ai) { return ai->HasRole(BOT_ROLE_HEAL); }

    void BrainTick(Match& m, Battleground* bg, BattlegroundMap* bgMap)
    {
        uint32 now = GameTime::GetGameTimeMS();
        bool fight = bg->GetStatus() == STATUS_IN_PROGRESS;

        struct U { ArenaBot* ab; Creature* c; bot_ai* ai; bool alive; bool healer; bool melee; };
        std::vector<U> units;
        for (ArenaBot& ab : m.bots)
        {
            Creature const* cb = BotDataMgr::FindBot(ab.entry);
            if (!cb || !cb->IsInWorld() || !cb->GetBotAI())
                continue;
            Creature* c = const_cast<Creature*>(cb);
            bot_ai* ai = c->GetBotAI();
            units.push_back(U{ &ab, c, ai, c->IsAlive(), IsHealer(ai), ai->ArenaIsMelee() });
        }

        if (units.empty() || !m.humans.empty())
            return; // Human matches use the bots' ordinary target selection, which includes players.

        for (U& u : units)
            if (!std::isfinite(u.c->GetPositionX()) || !std::isfinite(u.c->GetPositionY()) || !std::isfinite(u.c->GetPositionZ()))
            {
                TC_LOG_ERROR("npcbots", "BotArena: match #{} bot {} has a non-finite position on map {}; aborting the match", m.id, u.c->GetName(), m.mapId);
                std::string err;
                Stop(m.id, err);
                return;
            }

        // 1. stealth openers: rogues / feral druids stealth before the gates open and whenever out of combat
        {
            for (U& u : units)
            {
                if (!BrainFor(u.ab->team).stealthOpeners)
                    continue;
                if (!u.alive || u.c->IsInCombat() || u.c->HasAuraType(SPELL_AURA_MOD_STEALTH))
                    continue;
                uint32 spell = 0;
                if (u.ab->cs.cls == BOT_CLASS_ROGUE)
                    spell = SPELL_ROGUE_STEALTH;
                else if (u.ab->cs.cls == BOT_CLASS_DRUID && u.ab->cs.spec == BOT_SPEC_DRUID_FERAL)
                    spell = SPELL_DRUID_PROWL;
                if (!spell || now - u.ab->lastStealthMs < 3000)
                    continue;
                u.ab->lastStealthMs = now;
                u.c->CastSpell(u.c, spell, true);
            }
        }

        if (!fight)
            return;

        // 2. focus fire: one kill target per team, with hysteresis
        {
            for (int t = 0; t < 2; ++t)
            {
                uint32 team = t == 0 ? ALLIANCE : HORDE;
                BrainParams const& bp = _brainTeam[t];
                if (!bp.focusFire)
                {
                    for (U& u : units)
                        if (u.ab->team == team && u.ai)
                            u.ai->SetArenaTarget(ObjectGuid::Empty);
                    continue;
                }
                // our melee positions (for the distance term)
                std::vector<Creature*> ourMelee;
                for (U& u : units)
                    if (u.ab->team == team && u.alive && u.melee && !u.healer)
                        ourMelee.push_back(u.c);

                Unit* best = nullptr;
                float bestScore = 1.0e9f;
                float curScore = 1.0e9f;
                Unit* cur = !m.killTarget[t].IsEmpty() ? ObjectAccessor::GetUnit(*units.front().c, m.killTarget[t]) : nullptr;
                if (cur && (!cur->IsAlive() || !cur->IsInWorld()))
                    cur = nullptr;
                for (U& e : units)
                {
                    if (e.ab->team == team || !e.alive)
                        continue;
                    float score = e.c->GetHealthPct();
                    if (e.healer) score -= bp.healerBias;
                    if (IsCrowdControlled(e.c)) score -= bp.ccBonus;
                    if (!ourMelee.empty())
                    {
                        float d = 0;
                        for (Creature* mc : ourMelee) d += mc->GetExactDist2d(e.c);
                        score += bp.distWeight * (d / ourMelee.size());
                    }
                    if (e.c->GetGUID() == m.killTarget[t]) curScore = score;
                    if (score < bestScore) { bestScore = score; best = e.c; }
                }
                if (best)
                {
                    bool swap = !cur || (best != cur && bestScore < curScore - bp.swapMargin && now - m.killTargetSinceMs[t] >= bp.minTargetHoldMs);
                    if (swap)
                    {
                        m.killTarget[t] = best->GetGUID();
                        m.killTargetSinceMs[t] = now;
                        TC_LOG_DEBUG("npcbots", "BotArena: match #{} team {} kill target -> {}", m.id, t == 0 ? "A" : "H", best->GetName());
                    }
                }
                for (U& u : units)
                    if (u.ab->team == team && u.ai)
                        u.ai->SetArenaTarget(u.healer ? ObjectGuid::Empty : m.killTarget[t]);
            }
        }

        // 3. kiting: ranged casters and healers step away from an enemy melee in their face
        for (U& u : units)
        {
            BrainParams const& kp = BrainFor(u.ab->team);
            if (!u.alive || u.melee || !u.ai || u.ab->kiteUntilMs)
                continue;
            if (u.c->GetHealthPct() < kp.kiteHealthMin || now - u.ab->lastKiteMs < kp.kiteCooldownMs)
                continue;
            if (u.ai->ArenaIsCasting() || IsCrowdControlled(u.c) || u.c->HasAuraType(SPELL_AURA_MOD_ROOT))
                continue;
            Creature* threat = nullptr;
            float threatDist = kp.kiteTrigger;
            for (U& e : units)
                if (e.ab->team != u.ab->team && e.alive && e.melee)
                {
                    float d = u.c->GetExactDist2d(e.c);
                    if (d < threatDist) { threatDist = d; threat = e.c; }
                }
            if (!threat)
                continue;
            float ang = threat->GetAbsoluteAngle(u.c); // direction from threat to us
            float x = u.c->GetPositionX() + std::cos(ang) * kp.kiteDist;
            float y = u.c->GetPositionY() + std::sin(ang) * kp.kiteDist;
            float z = bgMap ? bgMap->GetHeight(x, y, u.c->GetPositionZ() + 5.0f, true, 30.0f) : u.c->GetPositionZ();
            if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z) || z <= INVALID_HEIGHT || std::fabs(z - u.c->GetPositionZ()) > 8.0f)
                continue; // off the arena floor (pillar / pit) or degenerate: skip this step
            Position pos(x, y, z + 0.5f, ang);
            u.ai->SetBotCommandState(BOT_COMMAND_STAY, true, &pos);
            u.ab->kiteUntilMs = now + kp.kiteStayMs;
            u.ab->lastKiteMs = now;
        }
    }

    // ---------------------------------------------------------------- feeds, cameras, rotation
    void SendFeeds()
    {
        for (auto itr = _spectators.begin(); itr != _spectators.end();)
        {
            Player* p = ObjectAccessor::FindConnectedPlayer(itr->guid);
            if (!p)
            {
                itr = _spectators.erase(itr);
                continue;
            }
            Match* m = FindMatch(itr->matchId);
            Battleground* bg = m ? m->GetBG() : nullptr;
            if (!m || !bg)
            {
                if (p->GetDisplayId() == SPECTATOR_DISPLAY_ID && !sMapStore.LookupEntry(p->GetMapId())->IsBattleArena())
                    p->RestoreDisplayId();
                ++itr;
                continue;
            }
            if (p->GetMapId() != m->mapId && p->GetDisplayId() == SPECTATOR_DISPLAY_ID)
                p->RestoreDisplayId();

            std::vector<std::string> lines;
            lines.push_back(Trinity::StringFormat("S;{};{};{};{};{};{};{}", StateName(m->state), bg->GetElapsedTime() / IN_MILLISECONDS,
                uint32(m->arenaType), WinnerName(m->winner), m->mapId, m->id, uint32(bg->GetStatus())));
            uint32 i = 0;
            for (ArenaBot const& ab : m->bots)
            {
                ++i;
                Creature const* bot = BotDataMgr::FindBot(ab.entry);
                if (!bot)
                    continue;
                uint32 castId = 0; int32 castLeft = 0, castTotal = 0;
                if (Spell const* s = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL)) { castId = s->m_spellInfo->Id; castLeft = s->GetTimer(); castTotal = s->GetCastTime(); }
                else if (Spell const* ch = bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL)) { castId = ch->m_spellInfo->Id; castLeft = ch->GetTimer(); castTotal = ch->m_spellInfo->GetDuration(); }
                Powers pt = bot->GetPowerType();
                lines.push_back(Trinity::StringFormat("B;{};{};{};{};{};{};{};{};{};{};{};{};{};{};{};{:.1f};{:.1f}", i,
                    ab.team == ALLIANCE ? "A" : "H", bot->GetName(), uint32(ab.cs.cls), uint32(ab.cs.spec),
                    bot->GetHealth(), bot->GetMaxHealth(), bot->GetPower(pt), bot->GetMaxPower(pt), uint32(pt),
                    bot->IsAlive() ? 1 : 0, bot->GetVictim() ? bot->GetVictim()->GetName() : "", castId, castLeft, castTotal,
                    bot->GetPositionX(), bot->GetPositionY()));
            }
            i = 0;
            for (ArenaBot const& ab : m->bots)
            {
                ++i;
                Creature const* bot = BotDataMgr::FindBot(ab.entry);
                if (!bot)
                    continue;
                std::vector<std::pair<int, std::string>> auras;
                for (auto const& [spellId, app] : bot->GetAppliedAuras())
                {
                    Aura const* aura = app->GetBase();
                    SpellInfo const* si = aura ? aura->GetSpellInfo() : nullptr;
                    if (!aura || !si || si->IsPassive() || aura->GetDuration() <= 0 || aura->GetMaxDuration() <= 0 || aura->GetMaxDuration() > 5 * MINUTE * IN_MILLISECONDS)
                        continue;
                    bool cc = si->HasAura(SPELL_AURA_MOD_STUN) || si->HasAura(SPELL_AURA_MOD_FEAR) || si->HasAura(SPELL_AURA_MOD_CONFUSE)
                        || si->HasAura(SPELL_AURA_MOD_ROOT) || si->HasAura(SPELL_AURA_MOD_SILENCE) || si->HasAura(SPELL_AURA_MOD_PACIFY)
                        || si->HasAura(SPELL_AURA_MOD_PACIFY_SILENCE) || si->HasAura(SPELL_AURA_TRANSFORM) || si->HasAura(SPELL_AURA_MOD_DISARM)
                        || si->HasAura(SPELL_AURA_MOD_POSSESS) || si->HasAura(SPELL_AURA_MOD_CHARM);
                    char flag = cc ? 'c' : (app->IsPositive() ? 'b' : 'd');
                    auras.emplace_back(cc ? 0 : (flag == 'd' ? 1 : 2), Trinity::StringFormat("{}:{}:{}", spellId, aura->GetDuration(), flag));
                }
                if (auras.empty())
                    continue;
                std::stable_sort(auras.begin(), auras.end(), [](auto const& a, auto const& b) { return a.first < b.first; });
                std::string line = Trinity::StringFormat("A;{};", i);
                uint32 n = 0;
                for (auto const& [_, text] : auras)
                {
                    if (n++ >= 8 || line.size() + text.size() > 230) break;
                    if (n > 1) line += ',';
                    line += text;
                }
                lines.push_back(line);
            }
            uint32 now = GameTime::GetGameTimeMS();
            uint32 sent = 0;
            for (CastEvent const& ev : m->events)
            {
                if (ev.seq <= itr->lastSentSeq) continue;
                if (sent++ >= 8) break;
                lines.push_back(Trinity::StringFormat("E;{};{};{};{};{}", ev.seq, ev.casterIdx, ev.spellId, ev.targetIdx, now - ev.timeMs));
                itr->lastSentSeq = ev.seq;
            }
            for (std::string const& line : lines)
            {
                WorldPackets::Chat::Chat packet;
                packet.Initialize(CHAT_MSG_WHISPER, LANG_ADDON, p, p, "BOTARENA\t" + line);
                p->SendDirectMessage(packet.Write());
            }
            ++itr;
        }
    }

    void UpdateAutoCameras()
    {
        uint32 now = GameTime::GetGameTimeMS();
        for (Spectator& s : _spectators)
        {
            if (!s.camAuto && !s.initialViewPending)
                continue;
            Player* p = ObjectAccessor::FindConnectedPlayer(s.guid);
            Match* m = FindMatch(s.matchId);
            if (!p || !m || p->IsBeingTeleported() || p->GetMapId() != m->mapId)
                continue;
            if (s.initialViewPending)
            {
                // One initial team viewpoint after worldport acknowledgement; never enable auto switching.
                std::string err;
                if (!m->bots.empty() && SetCamera(p, m->bots.front(), err))
                    s.initialViewPending = false;
                continue;
            }
            ArenaBot const* best = nullptr;
            float bestPct = 1.0e9f;
            for (ArenaBot const& ab : m->bots)
            {
                Creature const* bot = BotDataMgr::FindBot(ab.entry);
                if (!bot || !bot->IsAlive() || !bot->IsInWorld())
                    continue;
                float pct = bot->GetHealthPct();
                if (!bot->IsInCombat()) pct += 50.0f;
                if (pct < bestPct) { bestPct = pct; best = &ab; }
            }
            if (!best)
                continue;
            WorldObject* cur = p->GetViewpoint();
            Creature const* curBot = cur ? cur->ToCreature() : nullptr;
            bool curOk = curBot && curBot->IsAlive() && curBot->IsInWorld();
            bool switchNow = (s.camLastMs == 0) || !curOk || (now - s.camLastMs >= _camSwitchMs);
            Creature const* bot = BotDataMgr::FindBot(best->entry);
            if (curOk && switchNow && s.camLastMs != 0 && bot && bot->IsInCombat() && bot->GetHealthPct() > 35.0f)
                switchNow = false;
            if (curOk && !switchNow)
                continue;
            if (bot && cur != bot)
            {
                std::string err;
                if (SetCamera(p, *best, err))
                    s.camLastMs = now;
            }
        }
    }

    // Spectators whose match ended are moved to the featured match once it is up.
    void UpdateRejoins()
    {
        uint32 now = GameTime::GetGameTimeMS();
        Match* f = Featured();
        for (Spectator& s : _spectators)
        {
            Match* m = FindMatch(s.matchId);
            if (m && m->Running())
                continue;
            if (!f)
                continue;
            if (!s.rejoinAtMs)
            {
                s.rejoinAtMs = now + 3000;
                continue;
            }
            if (now < s.rejoinAtMs)
                continue;
            if (Player* p = ObjectAccessor::FindConnectedPlayer(s.guid))
            {
                std::string err;
                bool wasAuto = s.camAuto;
                if (Spectate(p, f->id, err))
                    s.camAuto = wasAuto;
            }
        }
    }

    void UpdateAuto(uint32 diff)
    {
        if (RunningCount() > 0)
        {
            _autoTimerMs = 0;
            return;
        }
        _autoTimerMs += diff;
        if (_autoTimerMs < _autoDelayMs)
            return;
        _autoTimerMs = 0;
        std::string err;
        StartRandom(3, BATTLEGROUND_AA, "random", "random", false, err);
    }

    void UpdateBatch(uint32 diff)
    {
        if (_batchRetryMs > diff) { _batchRetryMs -= diff; return; }
        _batchRetryMs = 1000;
        if (!_batch.active)
            return;
        if (_batch.done >= _batch.total)
        {
            _batch.active = false;
            TC_LOG_INFO("npcbots", "BotArena: batch finished: {} matches, A {} H {} draws {} in {}s", _batch.total, _batch.winsA, _batch.winsH, _batch.draws, (GameTime::GetGameTimeMS() - _batch.startedAtMs) / IN_MILLISECONDS);
            return;
        }
        std::string err;
        while (_batch.started < _batch.total && RunningCount() < _batch.concurrency)
        {
            if (!StartRandom(_batch.type, _batch.arena, _batch.compA, _batch.compH, true, err))
            {
                if (err.rfind("capacity:", 0) != 0)
                    TC_LOG_ERROR("npcbots", "BotArena: batch start failed: {}", err);
                break;
            }
            ++_batch.started;
        }
    }

public:
    // Start with preset/explicit/random comps as strings; "random" picks a preset of the right size.
    bool StartRandom(uint8 type, BattlegroundTypeId arena, std::string compAStr, std::string compHStr, bool fromBatch, std::string& err)
    {
        std::vector<Preset const*> presets = PresetsForSize(type);
        auto pick = [&](std::string& s)
        {
            if (s.empty() || Lower(s) == "random")
            {
                if (presets.empty()) return false;
                s = presets[urand(0, presets.size() - 1)]->name;
            }
            return true;
        };
        if (!pick(compAStr) || !pick(compHStr))
        {
            err = Trinity::StringFormat("no presets for {}v{}", uint32(type), uint32(type));
            return false;
        }
        std::vector<ClassSpec> compA, compH;
        if (!ParseComp(compAStr, compA, err) || !ParseComp(compHStr, compH, err))
            return false;
        return Start(type, arena, compA, compH, compAStr, compHStr, fromBatch, err) != nullptr;
    }

private:
    std::vector<std::unique_ptr<Match>> _matches;
    std::deque<std::string> _recent;
    uint32 _nextMatchId = 0;
    std::vector<Spectator> _spectators;
    Batch _batch;
    uint32 _batchRetryMs = 0;
    BrainParams _brain;          // shared defaults
    BrainParams _brainTeam[2];   // per-team overrides (A, H) for A/B tuning
    uint32 _feedTimer = 0;
    uint32 _camTimer = 0;
    uint32 _camSwitchMs = 20000;
    uint32 _leaveDelayMs = 15000;
    uint32 _maxDurationMs = 15 * MINUTE * IN_MILLISECONDS;
    bool _auto = false;
    uint32 _autoDelayMs = 20000;
    uint32 _autoTimerMs = 0;
};

#define sBotArenaMgr BotArenaMgr::instance()

template<typename... Args>
static void Msg(ChatHandler* handler, std::string_view fmt, Args&&... args)
{
    handler->SendSysMessage(Trinity::StringFormat(fmt::runtime(fmt), std::forward<Args>(args)...));
}

class botarena_world : public WorldScript
{
public:
    botarena_world() : WorldScript("botarena_world") { }
    void OnUpdate(uint32 diff) override { sBotArenaMgr->Update(diff); }
};

class botarena_commands : public CommandScript
{
public:
    botarena_commands() : CommandScript("botarena_commands") { }

    ChatCommandTable GetCommands() const override
    {
        static ChatCommandTable botarenaTable =
        {
            { "lobby", HandleLobby, rbac::RBAC_PERM_COMMAND_GM, Console::Yes },
            { "view", HandleView, rbac::RBAC_PERM_COMMAND_HELP, Console::No },
            { "start",    HandleStart,    rbac::RBAC_PERM_COMMAND_GM, Console::Yes },
            { "stop",     HandleStop,     rbac::RBAC_PERM_COMMAND_GM, Console::Yes },
            { "status",   HandleStatus,   rbac::RBAC_PERM_COMMAND_GM, Console::Yes },
            { "json",     HandleJson,     rbac::RBAC_PERM_COMMAND_GM, Console::Yes },
            { "spectate", HandleSpectate, rbac::RBAC_PERM_COMMAND_GM, Console::Yes },
            { "cam",      HandleCam,      rbac::RBAC_PERM_COMMAND_GM, Console::Yes },
            { "auto",     HandleAuto,     rbac::RBAC_PERM_COMMAND_GM, Console::Yes },
            { "batch",    HandleBatch,    rbac::RBAC_PERM_COMMAND_GM, Console::Yes },
            { "brain",    HandleBrain,    rbac::RBAC_PERM_COMMAND_GM, Console::Yes },
            { "comps",    HandleComps,    rbac::RBAC_PERM_COMMAND_GM, Console::Yes },
            { "gear",     HandleGear,     rbac::RBAC_PERM_COMMAND_GM, Console::Yes },
        };
        static ChatCommandTable commandTable = { { "botarena", botarenaTable } };
        return commandTable;
    }

    // Guests may only control their own registered spectator viewpoint.
    static bool HandleView(ChatHandler* handler, Tail args)
    {
        auto a = Split(args);
        if (a.size() != 1 || !handler->GetPlayer()) return false;
        std::string err;
        if (!sBotArenaMgr->Camera(handler->GetPlayer(), a[0], err)) { Msg(handler, "{}", err); return false; }
        return true;
    }

    static bool HandleLobby(ChatHandler* handler, Tail args)
    {
        // Only the local SOAP controller may provision loadouts or start human matches.
        if (handler->GetSession()) return false;
        auto a = Split(args); std::string err;
        if (a.size() == 2 && (a[0] == "leave" || a[0] == "logout"))
        {
            Player* p = ObjectAccessor::FindConnectedPlayerByName(a[1]);
            if (p)
            {
                sBotArenaMgr->ForgetSpectator(p);
                if (p->InBattleground()) p->LeaveBattleground(true, true);
                p->SetGameMaster(false); p->SetGMVisible(true); p->RestoreDisplayId();
                if (a[0] == "logout") p->GetSession()->LogoutPlayer(true);
            }
            Msg(handler, "LOBBY_OK left"); return true;
        }
        if (a.size() == 3 && a[0] == "build")
        {
            auto id = Trinity::StringTo<uint32>(a[2]);
            if (!id || !sBotArenaMgr->PreparePlayer(ObjectAccessor::FindConnectedPlayerByName(a[1]), *id, err))
            { Msg(handler, "LOBBY_ERROR {}", err); return false; }
            Msg(handler, "LOBBY_OK prepared"); return true;
        }
        if (a.size() >= 4 && a[0] == "match")
        {
            auto size = Trinity::StringTo<uint8>(a[1]);
            bool bots = a[2] == "bots";
            if (!size || (*size != 2 && *size != 3) || (!bots && a[2] != "players") || (bots ? (a.size() < 4u || a.size() > 3u + *size) : a.size() != 3u + *size * 2)) return false;
            std::vector<Player*> pa, ph; std::set<ObjectGuid> seen;
            for (size_t i=3; i<a.size(); ++i)
            {
                Player* p = ObjectAccessor::FindConnectedPlayerByName(a[i]);
                if (!p || p->InBattleground() || p->IsInCombat() || p->IsBeingTeleported() || p->GetLevel() != 80 || !seen.insert(p->GetGUID()).second)
                { Msg(handler, "LOBBY_ERROR player unavailable"); return false; }
                (i < 3u + *size ? pa : ph).push_back(p);
            }
            std::vector<ClassSpec> ca, ch;
            std::string opponent = "players";
            static std::string previous[4];
            if (bots)
            {
                // Fill only vacant allied slots; both invited humans stay on Gold.
                bool healer = std::any_of(pa.begin(), pa.end(), [](Player* p) {
                    uint8 group = p->GetActiveTalentGroup();
                    return p->HasTalent(53563, group) || p->HasTalent(47540, group) ||
                        p->HasTalent(48438, group) || p->HasTalent(61295, group) || p->HasTalent(34861, group);
                });
                while (ca.size() + pa.size() < *size)
                {
                    if (!healer) { ca.push_back({5,13}); healer = true; }
                    else ca.push_back(ca.empty() ? ClassSpec{8,24} : ClassSpec{1,1});
                }
                auto choices = PresetsForSize(*size);
                if (choices.size() > 1)
                    choices.erase(std::remove_if(choices.begin(), choices.end(), [&](Preset const* p) { return previous[*size] == p->name; }), choices.end());
                if (choices.empty()) { Msg(handler, "LOBBY_ERROR no opponent compositions"); return false; }
                opponent = choices[urand(0, choices.size()-1)]->name;
                if (!ParseComp(opponent, ch, err)) { Msg(handler, "LOBBY_ERROR {}", err); return false; }
            }
            auto* m = sBotArenaMgr->Start(*size, BATTLEGROUND_AA, ca, ch, "players-and-bots", opponent, false, err, pa, ph);
            if (!m) { Msg(handler, "LOBBY_ERROR {}", err); return false; }
            if (bots) previous[*size] = opponent;
            Msg(handler, "LOBBY_OK match {}", m->id); return true;
        }
        Msg(handler, "LOBBY_ERROR invalid request"); return false;
    }

    static std::vector<std::string> Split(std::string_view args)
    {
        std::vector<std::string> out;
        std::string cur;
        for (char c : args)
        {
            if (c == ' ' || c == '\t') { if (!cur.empty()) { out.push_back(cur); cur.clear(); } }
            else cur += c;
        }
        if (!cur.empty()) out.push_back(cur);
        return out;
    }

    static Player* ResolvePlayer(ChatHandler* handler, std::vector<std::string> const& args, size_t nameIdx)
    {
        if (args.size() > nameIdx)
            return ObjectAccessor::FindConnectedPlayerByName(args[nameIdx]);
        return handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
    }

    // [type] [arena] [compA] [compH]
    static bool ParseStartArgs(std::vector<std::string> const& a, size_t& i, uint8& type, BattlegroundTypeId& arena, std::string& compA, std::string& compH)
    {
        type = 3; arena = BATTLEGROUND_AA; compA = "random"; compH = "random";
        if (i < a.size())
        {
            std::string t = Lower(a[i]);
            if (t == "2" || t == "2v2") { type = 2; ++i; }
            else if (t == "3" || t == "3v3") { type = 3; ++i; }
            else if (t == "5" || t == "5v5") { type = 5; ++i; }
        }
        if (i < a.size() && ParseArena(a[i], arena)) ++i;
        if (i < a.size()) compA = a[i++];
        if (i < a.size()) compH = a[i++];
        return true;
    }

    static bool HandleStart(ChatHandler* handler, Tail args)
    {
        std::vector<std::string> a = Split(args);
        size_t i = 0; uint8 type; BattlegroundTypeId arena; std::string compA, compH;
        ParseStartArgs(a, i, type, arena, compA, compH);
        std::string err;
        if (!sBotArenaMgr->StartRandom(type, arena, compA, compH, false, err))
        {
            Msg(handler, "BotArena: {}", err);
            handler->SetSentErrorMessage(true);
            return false;
        }
        Msg(handler, "BotArena: match started ({}v{}), {} running. Use '.botarena spectate' to watch.", uint32(type), uint32(type), sBotArenaMgr->RunningCount());
        return true;
    }

    static bool HandleStop(ChatHandler* handler, Tail args)
    {
        std::vector<std::string> a = Split(args);
        std::string err;
        if (!a.empty() && Lower(a[0]) == "all")
        {
            sBotArenaMgr->StopAll();
            handler->SendSysMessage("BotArena: everything stopped (matches, batch, auto).");
            return true;
        }
        uint32 id = a.empty() ? 0 : Trinity::StringTo<uint32>(a[0]).value_or(0);
        if (!sBotArenaMgr->Stop(id, err))
        {
            Msg(handler, "BotArena: {}", err);
            return false;
        }
        handler->SendSysMessage("BotArena: match stopped.");
        return true;
    }

    static bool HandleStatus(ChatHandler* handler) { handler->SendSysMessage(sBotArenaMgr->StatusText()); return true; }
    static bool HandleJson(ChatHandler* handler) { handler->SendSysMessage(sBotArenaMgr->StatusJson()); return true; }

    // spectate [player] [matchId]
    static bool HandleSpectate(ChatHandler* handler, Tail args)
    {
        std::vector<std::string> a = Split(args);
        uint32 matchId = 0;
        if (!a.empty() && Trinity::StringTo<uint32>(a.back()))
        {
            matchId = *Trinity::StringTo<uint32>(a.back());
            a.pop_back();
        }
        Player* p = ResolvePlayer(handler, a, 0);
        if (!p) { handler->SendSysMessage("BotArena: no player (pass a player name from console)."); return false; }
        std::string err;
        if (!sBotArenaMgr->Spectate(p, matchId, err)) { Msg(handler, "BotArena: {}", err); return false; }
        Msg(handler, "BotArena: {} is now spectating.", p->GetName());
        return true;
    }

    static bool HandleCam(ChatHandler* handler, Tail args)
    {
        std::vector<std::string> a = Split(args);
        if (a.empty()) { handler->SendSysMessage("Usage: .botarena cam <1-10|botname|auto|off> [player]"); return false; }
        Player* p = ResolvePlayer(handler, a, 1);
        if (!p) { handler->SendSysMessage("BotArena: no player (pass a player name from console)."); return false; }
        std::string err;
        if (!sBotArenaMgr->Camera(p, a[0], err)) { Msg(handler, "BotArena: {}", err); return false; }
        Msg(handler, "BotArena: camera of {} -> {}", p->GetName(), a[0]);
        return true;
    }

    static bool HandleAuto(ChatHandler* handler, Tail args)
    {
        std::vector<std::string> a = Split(args);
        if (a.empty()) { Msg(handler, "BotArena: auto is {}", sBotArenaMgr->IsAuto() ? "on" : "off"); return true; }
        bool on = Lower(a[0]) == "on" || a[0] == "1";
        uint32 delay = a.size() > 1 ? Trinity::StringTo<uint32>(a[1]).value_or(0) : 0;
        sBotArenaMgr->SetAuto(on, delay);
        Msg(handler, "BotArena: auto {}", on ? "on" : "off");
        return true;
    }

    // batch <count> <concurrency> [type] [arena] [compA] [compH] | batch stop | batch status
    static bool HandleBatch(ChatHandler* handler, Tail args)
    {
        std::vector<std::string> a = Split(args);
        auto const& b = sBotArenaMgr->GetBatch();
        if (a.empty() || Lower(a[0]) == "status")
        {
            Msg(handler, "BotArena batch: {} total {} started {} done {} (A {} H {} draw {}) concurrency {} {}v{} {} vs {}",
                b.active ? "active" : "inactive", b.total, b.started, b.done, b.winsA, b.winsH, b.draws, b.concurrency, uint32(b.type), uint32(b.type), b.compA, b.compH);
            return true;
        }
        if (Lower(a[0]) == "stop")
        {
            sBotArenaMgr->StopBatch();
            handler->SendSysMessage("BotArena: batch stopped (running matches finish).");
            return true;
        }
        uint32 count = Trinity::StringTo<uint32>(a[0]).value_or(0);
        if (!count) { handler->SendSysMessage("Usage: .botarena batch <count> <concurrency> [2|3|5] [arena] [compA] [compH]"); return false; }
        uint32 conc = a.size() > 1 ? Trinity::StringTo<uint32>(a[1]).value_or(1) : 1;
        size_t i = 2; uint8 type; BattlegroundTypeId arena; std::string compA, compH;
        ParseStartArgs(a, i, type, arena, compA, compH);
        std::string err;
        if (!sBotArenaMgr->StartBatch(count, conc, type, arena, compA, compH, err)) { Msg(handler, "BotArena: {}", err); return false; }
        Msg(handler, "BotArena: batch of {} matches started (concurrency {}).", count, conc);
        return true;
    }

    // brain show | reload | set <key> <value> | save
    static bool HandleBrain(ChatHandler* handler, Tail args)
    {
        std::vector<std::string> a = Split(args);
        BrainParams& bp = sBotArenaMgr->Brain();
        if (a.empty() || Lower(a[0]) == "show")
        {
            Msg(handler, "ArenaBrain A: {}", sBotArenaMgr->BrainFor(ALLIANCE).Show());
            Msg(handler, "ArenaBrain H: {}", sBotArenaMgr->BrainFor(HORDE).Show());
            return true;
        }
        if (Lower(a[0]) == "reload")
        {
            uint32 n = bp.LoadFile(sBotArenaMgr->ParamsPath());
            sBotArenaMgr->SyncBrains();
            Msg(handler, "ArenaBrain: loaded {} parameter(s) from {} for both teams: {}", n, sBotArenaMgr->ParamsPath(), bp.Show());
            return true;
        }
        std::string cmd = Lower(a[0]);
        if ((cmd == "set" || cmd == "seta" || cmd == "seth") && a.size() >= 3)
        {
            bool ok = true;
            if (cmd == "set") { ok = bp.Set(a[1], a[2]); sBotArenaMgr->SyncBrains(); }
            else ok = sBotArenaMgr->BrainFor(cmd == "seta" ? ALLIANCE : HORDE).Set(a[1], a[2]);
            if (!ok) { Msg(handler, "ArenaBrain: unknown parameter or bad value: {} {}", a[1], a[2]); return false; }
            Msg(handler, "ArenaBrain A: {}", sBotArenaMgr->BrainFor(ALLIANCE).Show());
            Msg(handler, "ArenaBrain H: {}", sBotArenaMgr->BrainFor(HORDE).Show());
            return true;
        }
        handler->SendSysMessage("Usage: .botarena brain show | reload | set|setA|setH <key> <value>");
        return false;
    }

    // gear reload | gear show <class> <spec>
    static bool HandleGear(ChatHandler* handler, Tail args)
    {
        std::vector<std::string> a = Split(args);
        if (!a.empty() && Lower(a[0]) == "reload")
        {
            Msg(handler, "BotArena gear: loaded {} pieces", sBotArenaMgr->LoadGear());
            return true;
        }
        if (a.size() >= 3 && Lower(a[0]) == "show")
        {
            uint8 cls = ParseClass(Lower(a[1]));
            uint8 spec = ParseSpec(cls, Lower(a[2]));
            if (!cls || !spec) { handler->SendSysMessage("BotArena gear: unknown class/spec"); return false; }
            Msg(handler, "BotArena gear for {} {}:\n{}", a[1], a[2], sBotArenaMgr->GearText(cls, spec));
            return true;
        }
        if (a.size() >= 2 && Lower(a[0]) == "findench")
        {
            std::string needle = Lower(std::string(args.substr(args.find(a[1]))));
            uint32 n = 0;
            for (uint32 id = 0; id < sSpellItemEnchantmentStore.GetNumRows() && n < 40; ++id)
                if (SpellItemEnchantmentEntry const* e = sSpellItemEnchantmentStore.LookupEntry(id))
                    if (e->Name[0] && Lower(e->Name[0]).find(needle) != std::string::npos)
                    {
                        Msg(handler, "  {} = {}", id, e->Name[0]);
                        ++n;
                    }
            return true;
        }
        handler->SendSysMessage("Usage: .botarena gear reload | show <class> <spec> | findench <text>");
        return false;
    }

    static bool HandleComps(ChatHandler* handler)
    {
        for (Preset const& p : Presets)
            Msg(handler, "{:<12} {:<45} {}", p.name, p.comp, p.desc);
        handler->SendSysMessage("Classes: warrior paladin hunter rogue priest dk shaman mage warlock druid. Format: class:spec,class:spec,... or 'random'");
        return true;
    }
};

static void BotArenaCastHook(Creature* bot, Unit* target, uint32 spellId)
{
    sBotArenaMgr->RecordCast(bot, target, spellId);
}

static Item* BotArenaGearHook(Creature* bot, uint8 botclass, uint8 spec, uint8 slot)
{
    return sBotArenaMgr->GearFor(bot, botclass, spec, slot);
}

class botarena_world_load : public WorldScript
{
public:
    botarena_world_load() : WorldScript("botarena_world_load") { }
    void OnStartup() override { sBotArenaMgr->LoadGear(); }
};

void AddSC_botarena()
{
    g_botCastHook = &BotArenaCastHook;
    g_botArenaGearHook = &BotArenaGearHook;
    new botarena_world_load();
    new botarena_world();
    new botarena_commands();
}
