#!/usr/bin/env python3
"""Idempotently apply the BotArena core modifications to the TrinityCore+NPCBots tree in server/.

Each patch is a (file, marker-present-check, old, new) substitution. Re-running is safe.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "server"
MARK = "//botarena"

PATCHES = [
    # Arena generation already assigns the requested spec before InitEquips runs.
    ("src/server/game/AI/NpcBots/bot_ai.cpp",
     "    if (IAmFree() && !me->IsSummon())\n        spec = BotDataMgr::SelectSpecForClass(_botclass);\n",
     "    if (IAmFree() && !me->IsSummon() && !(IsWanderer() && me->GetMap()->IsBattleArena())) //botarena: preserve the assigned arena spec\n        spec = BotDataMgr::SelectSpecForClass(_botclass);\n"),
    # 1. Battleground.h: bot-arena flag --------------------------------------------------------
    ("src/server/game/Battlegrounds/Battleground.h",
     "        void SetDeleteThis() { m_SetDeleteThis = true; }\n",
     "        void SetDeleteThis() { m_SetDeleteThis = true; }\n"
     "        //botarena\n"
     "        void SetBotArena(bool v) { m_isBotArena = v; }\n"
     "        bool IsBotArena() const { return m_isBotArena; }\n"
     "        //end botarena\n"),
    ("src/server/game/Battlegrounds/Battleground.h",
     "        BattlegroundBotMap m_Bots;\n",
     "        BattlegroundBotMap m_Bots;\n"
     "        bool m_isBotArena = false; //botarena\n"),
    # 2. Battleground.cpp: keep a bot-only arena alive -------------------------------------------
    ("src/server/game/Battlegrounds/Battleground.cpp",
     "    //npcbot\n    if (m_Bots.empty())\n    //end npcbot\n    if (!GetPlayersSize())\n",
     "    //npcbot\n    if (m_Bots.empty() && !(m_isBotArena && GetStatus() == STATUS_WAIT_JOIN)) //botarena\n    //end npcbot\n    if (!GetPlayersSize())\n"),
    ("src/server/game/Battlegrounds/Battleground.cpp",
     "        if (m_Players.empty() && !m_Bots.empty())\n        {\n            EndNow();\n",
     "        if (!m_isBotArena && m_Players.empty() && !m_Bots.empty()) //botarena\n        {\n            EndNow();\n"),
    ("src/server/game/Battlegrounds/Battleground.cpp",
     "        case STATUS_WAIT_JOIN:\n            if (GetPlayersSize())\n",
     "        case STATUS_WAIT_JOIN:\n            if (GetPlayersSize() || (m_isBotArena && !m_Bots.empty())) //botarena\n"),
    # 3. Arena.cpp: allow free (wandering) bots in arenas ---------------------------------------
    ("src/server/game/Battlegrounds/Arena.cpp",
     "    ASSERT(bot->IsNPCBot() && !bot->IsFreeBot());\n\n    bool const isInBattleground = IsPlayerInBattleground(bot->GetGUID());\n    Battleground::AddBot(bot);\n\n    uint32 botteam = bot->GetBotOwner()->GetBGTeam();\n",
     "    ASSERT(bot->IsNPCBot()); //botarena\n\n    bool const isInBattleground = IsPlayerInBattleground(bot->GetGUID());\n    Battleground::AddBot(bot);\n\n    uint32 botteam = !bot->IsFreeBot() ? bot->GetBotOwner()->GetBGTeam() : GetBotTeam(bot->GetGUID()); //botarena\n"),
    # 4. MapInstanced.h: expose CreateBattleground ------------------------------------------------
    ("src/server/game/Maps/MapInstanced.h",
     "        BattlegroundMap* CreateBattleground(uint32 InstanceId, Battleground* bg);\n",
     "    public: //botarena\n        BattlegroundMap* CreateBattleground(uint32 InstanceId, Battleground* bg);\n    private: //botarena\n"),
    # 5. botdatamgr.h: arena bot generation API -------------------------------------------------
    ("src/server/game/AI/NpcBots/botdatamgr.h",
     "    static bool GenerateBattlegroundBots(Player const* groupLeader, Group const* group, BattlegroundQueue* queue, PvPDifficultyEntry const* bracketEntry, GroupQueueInfo const* gqinfo);\n",
     "    static bool GenerateBattlegroundBots(Player const* groupLeader, Group const* group, BattlegroundQueue* queue, PvPDifficultyEntry const* bracketEntry, GroupQueueInfo const* gqinfo);\n"
     "    static bool GenerateArenaBots(std::vector<std::pair<uint8, uint8>> const& classSpecs, uint32 mapId, uint32 team, PvPDifficultyEntry const* bracketEntry, NpcBotRegistry* registry); //botarena\n"),
    # 6. botdatamgr.cpp: forced spec + arena generator -----------------------------------------
    ("src/server/game/AI/NpcBots/botdatamgr.cpp",
     "        bool immediate, PvPDifficultyEntry const* bracketEntry, NpcBotRegistry* registry)\n    {\n        CreatureTemplateContainer const& all_templates = sObjectMgr->GetCreatureTemplates();\n",
     "        bool immediate, PvPDifficultyEntry const* bracketEntry, NpcBotRegistry* registry, uint8 forced_spec = 0 /*botarena*/)\n    {\n        CreatureTemplateContainer const& all_templates = sObjectMgr->GetCreatureTemplates();\n"),
    ("src/server/game/AI/NpcBots/botdatamgr.cpp",
     "        uint8 bot_spec = BotDataMgr::SelectSpecForClass(bot_class);\n",
     "        uint8 bot_spec = forced_spec ? forced_spec : BotDataMgr::SelectSpecForClass(bot_class); //botarena\n"),
    ("src/server/game/AI/NpcBots/botdatamgr.cpp",
     "    bool GenerateDungeonBotsToSpawn(Player const* owner, uint32 bots_count, std::array<uint8, 3>&& desired_roles)\n",
     r'''    //botarena
    bool GenerateArenaBotsToSpawn(std::vector<std::pair<uint8, uint8>> const& classSpecs, int32 map_id, int32 team, PvPDifficultyEntry const* bracketEntry, NpcBotRegistry* registry, uint32& spawned)
    {
        using NodeVec = std::vector<WanderNode const*>;

        if (_spareBotIdsPerClassMap.empty() || !bracketEntry)
            return false;

        std::array<NodeVec, 3> spawns_all{};
        auto& [spawns_a, spawns_h, spawns_n] = spawns_all;
        WanderNode::DoForAllWPs([map_id = map_id, &spawns_a = spawns_a, &spawns_h = spawns_h, &spawns_n = spawns_n](WanderNode const* wp) {
            MapEntry const* mapEntry = sMapStore.LookupEntry(wp->GetMapId());
            if (mapEntry && int32(mapEntry->ID) == map_id && wp->HasFlag(BotWPFlags::BOTWP_FLAG_SPAWN))
            {
                if (bot_ai::IsWanderNodeAvailableForBotFaction(wp, FACTION_TEMPLATE_ALLIANCE_DEFAULT, false, true))
                    spawns_a.emplace_back(wp);
                else if (bot_ai::IsWanderNodeAvailableForBotFaction(wp, FACTION_TEMPLATE_HORDE_DEFAULT, false, true))
                    spawns_h.emplace_back(wp);
                if (bot_ai::IsWanderNodeAvailableForBotFaction(wp, FACTION_TEMPLATE_NEUTRAL_HOSTILE, false, true))
                    spawns_n.emplace_back(wp);
            }
        });

        if ((team == ALLIANCE && spawns_a.empty()) || (team == HORDE && spawns_h.empty()))
        {
            BOT_LOG_ERROR("npcbots", "GenerateArenaBotsToSpawn: no spawn nodes for team {} on map {}", team, map_id);
            return false;
        }

        std::vector<std::pair<uint8, uint32>> picks;
        std::vector<uint8> specs;
        for (auto const& [bot_class, bot_spec] : classSpecs)
        {
            auto cit = _spareBotIdsPerClassMap.find(bot_class);
            if (cit == _spareBotIdsPerClassMap.cend())
            {
                BOT_LOG_ERROR("npcbots", "GenerateArenaBotsToSpawn: no spare bots of class {}", uint32(bot_class));
                return false;
            }
            std::vector<uint32> candidates;
            for (uint32 spareBotId : cit->second)
            {
                if (std::ranges::any_of(picks, [=](std::pair<uint8, uint32> const& p) { return p.second == spareBotId; }))
                    continue;
                NpcBotExtras const* orig_extras = ASSERT_NOTNULL(BotDataMgr::SelectNpcBotExtras(spareBotId));
                uint32 bot_faction = BotDataMgr::GetDefaultFactionForBotRaceClass(orig_extras->bclass, orig_extras->race);
                if (int32(BotDataMgr::GetTeamForFaction(bot_faction)) != team)
                    continue;
                if (BotDataMgr::GetMinLevelForBotClass(bot_class) > bracketEntry->MaxLevel)
                    continue;
                candidates.push_back(spareBotId);
            }
            if (candidates.empty())
            {
                BOT_LOG_ERROR("npcbots", "GenerateArenaBotsToSpawn: no spare bots of class {} for team {}", uint32(bot_class), team);
                return false;
            }
            picks.emplace_back(bot_class, Bcore::Containers::SelectRandomContainerElement(candidates));
            specs.push_back(bot_spec);
        }

        uint8 bracket = uint8(bracketEntry->MinLevel / 10);
        for (size_t i = 0; i < picks.size(); ++i)
        {
            if (!GenerateWanderingBotToSpawn(picks[i], bracket, spawns_a, spawns_h, spawns_n, true, bracketEntry, registry, specs[i]))
                return false;
            ++spawned;
        }

        CharacterDatabase.PExecute("UPDATE worldstates SET value = {} WHERE entry = {}", next_bot_id, uint32(BOT_GIVER_ENTRY));
        return true;
    }
    //end botarena

    bool GenerateDungeonBotsToSpawn(Player const* owner, uint32 bots_count, std::array<uint8, 3>&& desired_roles)
'''),
    ("src/server/game/AI/NpcBots/botdatamgr.cpp",
     "ItemPerBotClassPerBotCategoryMap const& BotDataMgr::GetWanderingBotsSortedGearMap()\n",
     r'''//botarena
bool BotDataMgr::GenerateArenaBots(std::vector<std::pair<uint8, uint8>> const& classSpecs, uint32 mapId, uint32 team, PvPDifficultyEntry const* bracketEntry, NpcBotRegistry* registry)
{
    uint32 spawned = 0;
    bool ok = sBotGen->GenerateArenaBotsToSpawn(classSpecs, int32(mapId), int32(team), bracketEntry, registry, spawned);
    if (!ok || spawned != classSpecs.size())
    {
        BOT_LOG_ERROR("npcbots", "GenerateArenaBots: spawned {}/{} bots for team {} on map {}", spawned, classSpecs.size(), team, mapId);
        return false;
    }
    return true;
}
//end botarena

ItemPerBotClassPerBotCategoryMap const& BotDataMgr::GetWanderingBotsSortedGearMap()
'''),
    # 7. script loader -------------------------------------------------------------------------
    ("src/server/scripts/Custom/custom_script_loader.cpp",
     "void AddCustomScripts()\n{\n}\n",
     "void AddSC_botarena(); //botarena\n\nvoid AddCustomScripts()\n{\n    AddSC_botarena(); //botarena\n}\n"),
    # 8. bot cast hook (for the spectator ability feed) ------------------------------------------
    ("src/server/game/AI/NpcBots/botmgr.h",
     "class TC_GAME_API BotMgr\n",
     "//botarena: called after a bot successfully starts casting a spell\nusing BotCastHookFn = void (*)(Creature* bot, Unit* target, uint32 spellId);\nTC_GAME_API extern BotCastHookFn g_botCastHook;\n//end botarena\n\nclass TC_GAME_API BotMgr\n"),
    ("src/server/game/AI/NpcBots/botmgr.cpp",
     "static std::list<BotMgr::delayed_teleport_callback_type> delayed_bot_teleports;\n",
     "static std::list<BotMgr::delayed_teleport_callback_type> delayed_bot_teleports;\nBotCastHookFn g_botCastHook = nullptr; //botarena\n"),
    ("src/server/game/AI/NpcBots/bot_ai.cpp",
     "    if (result != SPELL_CAST_OK)\n        return false;\n\n    if (!(triggered ||\n",
     "    if (result != SPELL_CAST_OK)\n        return false;\n\n    if (g_botCastHook) //botarena\n        g_botCastHook(me, victim, m_botSpellInfo->Id);\n\n    if (!(triggered ||\n"),
    # 9. ArenaBrain hooks --------------------------------------------------------------------------
    ("src/server/game/Battlegrounds/Battleground.h",
     "        typedef std::map<ObjectGuid, BattlegroundScore*> BattlegroundScoreMap;\n",
     "        typedef std::map<ObjectGuid, BattlegroundScore*> BattlegroundScoreMap;\n        [[nodiscard]] BattlegroundScoreMap const& GetBotScores() const { return BotScores; } //botarena\n"),
    ("src/server/game/AI/NpcBots/bot_ai.h",
     "    Battleground* GetBG() const { return _bg; }\n",
     "    Battleground* GetBG() const { return _bg; }\n    //botarena: forced kill target for arena bots (empty = none)\n    void SetArenaTarget(ObjectGuid guid) { _arenaTarget = guid; }\n    ObjectGuid GetArenaTarget() const { return _arenaTarget; }\n"),
    ("src/server/game/AI/NpcBots/bot_ai.h",
     "    ObjectGuid _lastTargetGuid;\n",
     "    ObjectGuid _lastTargetGuid;\n    ObjectGuid _arenaTarget; //botarena\n"),
    ("src/server/game/AI/NpcBots/bot_ai.cpp",
     "    if (mytar && me->HasAuraType(SPELL_AURA_MOD_TAUNT))\n        return { mytar, mytar };\n",
     "    if (mytar && me->HasAuraType(SPELL_AURA_MOD_TAUNT))\n        return { mytar, mytar };\n\n    //botarena: forced arena kill target\n    if (!_arenaTarget.IsEmpty())\n    {\n        if (Unit* at = ObjectAccessor::GetUnit(*me, _arenaTarget))\n            if (at->IsAlive() && at->IsInWorld() && me->GetMap() == at->FindMap() && CanBotAttack(at, byspell))\n                return { at, at };\n    }\n"),
    ("src/server/game/AI/NpcBots/bot_rogue_ai.cpp",
     "                if (!me->IsInCombat() && Rand() < 5 && me->HasAuraType(SPELL_AURA_MOD_STEALTH) &&\n",
     "                if (!me->IsInCombat() && Rand() < 5 && me->HasAuraType(SPELL_AURA_MOD_STEALTH) && !me->GetMap()->IsBattleArena() /*botarena*/ &&\n"),
    ("src/server/game/Battlegrounds/BattlegroundScore.h",
     "        uint32 GetKillingBlows() const    { return KillingBlows; }\n",
     "    public: //botarena\n        uint32 GetKillingBlows() const    { return KillingBlows; }\n"),
    ("src/server/game/AI/NpcBots/bot_ai.h",
     "    ObjectGuid GetArenaTarget() const { return _arenaTarget; }\n",
     "    ObjectGuid GetArenaTarget() const { return _arenaTarget; }\n    bool ArenaIsMelee() const { return IsMelee(); }\n    bool ArenaIsCasting() const { return IsCasting(); }\n"),
    # 10. ArenaBrain gear hook: a fixed item per slot for arena bots instead of generated gear -------------
    ("src/server/game/AI/NpcBots/botmgr.h",
     "//botarena: called after a bot successfully starts casting a spell\n",
     "//botarena: gear hook: returns a ready item (with enchants/gems) for a slot of a freshly spawned arena bot, or nullptr\nclass Item;\nusing BotGearHookFn = Item* (*)(Creature* bot, uint8 botclass, uint8 spec, uint8 slot);\nTC_GAME_API extern BotGearHookFn g_botArenaGearHook;\n//botarena: called after a bot successfully starts casting a spell\n"),
    ("src/server/game/AI/NpcBots/botmgr.cpp",
     "BotCastHookFn g_botCastHook = nullptr; //botarena\n",
     "BotCastHookFn g_botCastHook = nullptr; //botarena\nBotGearHookFn g_botArenaGearHook = nullptr; //botarena\n"),
    ("src/server/game/AI/NpcBots/bot_ai.cpp",
     "            Item* item = BotDataMgr::GenerateWanderingBotItem(gen_category, i, _botclass, lvl, max_item_level, fit_check);\n",
     "            bool from_hook = false; //botarena\n            Item* item = g_botArenaGearHook ? g_botArenaGearHook(me, _botclass, GetSpec(), i) : nullptr;\n            if (item) from_hook = true;\n            else item = BotDataMgr::GenerateWanderingBotItem(gen_category, i, _botclass, lvl, max_item_level, fit_check);\n"),
    ("src/server/game/AI/NpcBots/bot_ai.cpp",
     "                if (GetSpec() != BOT_SPEC_DEFAULT && BotDataMgr::GenerateWanderingBotItemEnchants(item, i, GetSpec())) {}\n",
     "                if (!from_hook && GetSpec() != BOT_SPEC_DEFAULT && BotDataMgr::GenerateWanderingBotItemEnchants(item, i, GetSpec())) {}\n"),
]


# BotArena supplies exact team starts. Generic wandering-bot spread can cross closed gates.
PATCHES.append((
    "src/server/game/AI/NpcBots/bot_ai.cpp",
    "    Battleground* bg = ASSERT_NOTNULL(GetBG());\n\n    if (bg->GetStatus() != STATUS_IN_PROGRESS && IsWanderer())",
    "    Battleground* bg = ASSERT_NOTNULL(GetBG());\n\n    if (bg->IsBotArena()) //botarena: keep the authoritative team spawn\n    {\n        SetBotCommandState(BOT_COMMAND_STAY);\n        return;\n    }\n\n    if (bg->GetStatus() != STATUS_IN_PROGRESS && IsWanderer())",
))

PATCHES += json.loads(pathlib.Path(__file__).with_name("benchmark_core_patches.json").read_text())

def main() -> int:
    applied = skipped = failed = 0
    for rel, old, new in PATCHES:
        path = ROOT / rel
        text = path.read_text()
        if new in text:
            skipped += 1
            continue
        if old not in text:
            print(f"FAILED: anchor not found in {rel}:\n{old[:120]!r}")
            failed += 1
            continue
        path.write_text(text.replace(old, new, 1))
        applied += 1
        print(f"patched {rel}")
    print(f"applied={applied} already={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
