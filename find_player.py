from steam.steamid import SteamID
from steam.steamid import from_url
from steam.webapi import WebAPI
from steam import game_servers as gs
import json
import requests
import concurrent.futures
import config
import logging

# this program checks if an invisible player is currently on a server
# To do:
#  detect presence via 3 bit shift register
#  Save all timed-out servers for a second attempt after all normal servers are queried,
# or maybe just try them again immediately?

# user = "The_New_Goy" #"76561197972375071"
# user = "OneJewToRuleThemAll"
# user = 9478325682 # YALE
user = "chubbeee"  # Rose
# user = "tukisboolukis"
# app_id = 60 #Ricochet
app_id = 440  # tf2
# app_id = 320 # hl2dm
# app_id = 4000 # gmod
# app_id = 300 # DoD
timeout_servers = []
api = WebAPI(config.api_key)
logger = logging.getLogger(__name__)


def config_logger():
    """set up and initialize logging"""
    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    file_handler = logging.FileHandler("find_player.log", "w", "utf-8")
    console_handler.setLevel(logging.DEBUG)
    file_handler.setLevel(logging.INFO)

    console_format = logging.Formatter("%(levelname)s - %(message)s")
    file_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_format)
    file_handler.setFormatter(file_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


def get_persona(identifier):
    """convert vanity url or SteamID into "personaname"""
    user_id = api.call("ISteamUser.ResolveVanityURL", vanityurl=identifier)
    # response code 42 means no match, try as steam ID
    if user_id["response"]["success"] == 42:
        user_id = SteamID(identifier)
    user_info = api.call("ISteamUser.GetPlayerSummaries", steamids=user_id)
    persona = user_info["response"]["players"][0]["personaname"]
    return persona


def get_game(id):
    """convert app_id into human readable game title"""
    title = requests.get(rf"https://api.steampowered.com/ICommunityService/GetApps/v1/?key={config.api_key}&appids[0]={id}")
    title = title.json()["response"]["apps"][0]["name"]
    return title


def get_servers(key, id):
    """get all non valve matchmaking servers that are not empty

    https://steamapi.xpaw.me/#IGameServersService/GetServerList
    """
    server_list = requests.get(
        rf"https://api.steampowered.com/IGameServersService/GetServerList/v1/?key={config.api_key}&filter=\appid\{str(app_id)}\empty\1\nor\1\gametype\valve&limit=4000"
    )
    server_list = server_list.json()["response"]["servers"]
    # log response to file for debugging
    try:
        with open("find_player.json", "w") as outfile:
            json.dump(server_list, outfile)
    except IOError:
        with open("find_player.json", "x") as outfile:
            json.dump(server_list, outfile)
    return server_list


def server_query(server, user_persona):
    # logger.debug(f"{server['addr']} , {server['name']} , {server['map']}\n")
    current_addr = server["addr"].split(":")
    current_addr[1] = int(current_addr[1])
    player_set = set()

    try:
        server_players = gs.a2s_players(tuple(current_addr), timeout=5)
        logger.debug(current_addr)
        for player in server_players:
            player_set.add(player["name"])
            # remove server regional tags ie; "[US]"
            if "] " in player["name"]:
                split_name = player["name"].split("] ")
                player_set.add(split_name[1])
            elif "]" in player["name"]:
                split_name = player["name"].split("]")
                player_set.add(split_name[1])
    except TimeoutError:
        logger.error(f"timeout error on: {server['name']}, IP-> {server['addr']}")
        timeout_servers.append(current_addr)
    except RuntimeError:
        logger.error(f"Runtime Error on: {server['name']}, IP-> {server['addr']}")
    except OSError:
        logger.error(f"OS Error on: {server['name']}, IP-> {server['addr']}")

    if user_persona in player_set:
        logger.info(f"{user_persona} is playing on: {server['name']}\nsteam://connect/{server['addr']}")
        return f"{user_persona} is playing on: {server['name']}\nsteam://connect/{server['addr']}"

    return None


def main():
    config_logger()
    try:
        user_persona = get_persona(user)
        game = get_game(app_id)
        server_list = get_servers(config.api_key, app_id)
        logger.info(f"Searching for {user_persona} on {len(server_list)} {game} servers...")

        player_online = f"{user_persona} was not found."
        # https://www.digitalocean.com/community/tutorials/how-to-use-threadpoolexecutor-in-python-3#step-3-processing-exceptions-from-functions-run-in-threads
        with concurrent.futures.ThreadPoolExecutor(500) as executor:
            futures = []
            for server in server_list:
                futures.append(executor.submit(server_query, server, user_persona))
            for future in concurrent.futures.as_completed(futures):
                player_found = future.result()
                if player_found is not None:
                    logger.info(f"{user_persona} has been found!")
                    player_online = player_found

        logger.info(f"{player_online}")
        # requests.post(config.discord_webhook_url, { "content": f"{player_online}"} )
        logger.warning(f"Timeout errors on {len(timeout_servers)} servers.")
    except ConnectionError:
        logger.error(f"API connection error", exc_info=True)


if __name__ == "__main__":
    main()
