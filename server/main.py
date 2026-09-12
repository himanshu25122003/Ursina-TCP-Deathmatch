"""
Server script for hosting games
"""

import socket
import json
import time
import random
import threading
from art import *

PORT = 8888  # this should be same as you define in playit.gg dashboard
ADDR = "0.0.0.0"
MAX_PLAYERS = 10
MSG_SIZE = 4096

# Setup server socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind((ADDR, PORT))
s.listen(MAX_PLAYERS)

players = {}
players_lock = threading.Lock()


def generate_id(player_list: dict, max_players: int):
    """
    Generate a unique identifier

    Args:
        player_list (dict): dictionary of existing players
        max_players (int): maximum number of players allowed

    Returns:
        str: the unique identifier
    """
    while True:
        unique_id = str(random.randint(1, max_players))
        if unique_id not in player_list:
            return unique_id


def process_client_message(identifier: str, username: str, msg_json: dict):
    obj_type = msg_json.get("object")

    with players_lock:
        if identifier not in players:
            return

        if obj_type == "player":
            if "position" in msg_json:
                players[identifier]["position"] = msg_json["position"]
            if "rotation" in msg_json:
                players[identifier]["rotation"] = msg_json["rotation"]
            if "health" in msg_json:
                players[identifier]["health"] = msg_json["health"]
                players[identifier]["visible"] = msg_json["health"] > 0

        elif obj_type == "respawn":
            if "position" in msg_json:
                players[identifier]["position"] = msg_json["position"]
            players[identifier]["health"] = msg_json.get("health", 100)
            players[identifier]["visible"] = True

            respawn_msg = (json.dumps({
                "object": "player_respawn",
                "id": identifier,
                "position": players[identifier]["position"],
                "health": players[identifier]["health"]
            }) + "\n").encode("utf8")

            for player_id, p_info in list(players.items()):
                if player_id != identifier:
                    try:
                        p_info["socket"].sendall(respawn_msg)
                    except OSError:
                        pass
            return

        elif obj_type == "health_update":
            target_id = str(msg_json.get("id"))
            if target_id in players:
                players[target_id]["health"] = msg_json.get("health", 100)
                players[target_id]["visible"] = players[target_id]["health"] > 0

        # Broadcast to all other players with newline
        broadcast_bytes = (json.dumps(msg_json) + "\n").encode("utf8")
        for player_id, p_info in list(players.items()):
            if player_id != identifier:
                try:
                    p_info["socket"].sendall(broadcast_bytes)
                except OSError:
                    pass


def handle_messages(identifier: str):
    with players_lock:
        if identifier not in players:
            return
        client_info = players[identifier]
        conn: socket.socket = client_info["socket"]
        username = client_info["username"]
        recv_buffer = client_info.get("initial_buffer", "")

    decoder = json.JSONDecoder()

    while True:
        # First process any complete JSON objects already in buffer
        idx = 0
        while idx < len(recv_buffer):
            while idx < len(recv_buffer) and recv_buffer[idx] in ' \t\r\n':
                idx += 1
            if idx >= len(recv_buffer):
                recv_buffer = ""
                break
            try:
                msg_json, end_idx = decoder.raw_decode(recv_buffer, idx)
                recv_buffer = recv_buffer[end_idx:]
                idx = 0
            except json.JSONDecodeError:
                recv_buffer = recv_buffer[idx:]
                break

            process_client_message(identifier, username, msg_json)

        try:
            msg = conn.recv(MSG_SIZE)
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            break

        if not msg:
            break

        recv_buffer += msg.decode("utf8", errors="ignore")

    # Tell other players about player leaving
    leave_msg = (json.dumps({
        "id": identifier,
        "object": "player",
        "joined": False,
        "left": True
    }) + "\n").encode("utf8")

    with players_lock:
        for player_id, p_info in list(players.items()):
            if player_id != identifier:
                try:
                    p_info["socket"].sendall(leave_msg)
                except OSError:
                    pass

        print(f"Player {username} with ID {identifier} has left the game...")
        if identifier in players:
            del players[identifier]

    try:
        conn.close()
    except OSError:
        pass


def main():
    hostname = socket.gethostname()
    server_addr = f'{socket.gethostbyname(hostname)}:{PORT}'

    print("\nServer started, listening for new connections...")
    print(f'IPV4 Address = {server_addr}\n')
    tprint(server_addr)

    while True:
        conn, addr = s.accept()
        with players_lock:
            new_id = generate_id(players, MAX_PLAYERS)

        try:
            conn.sendall(f"{new_id}\n".encode("utf8"))
            raw_username = conn.recv(MSG_SIZE).decode("utf8", errors="ignore")
        except Exception as e:
            print(f"Handshake failed: {e}")
            conn.close()
            continue

        if "\n" in raw_username:
            username_parts = raw_username.split("\n", 1)
            username = username_parts[0].strip()
            initial_buffer = username_parts[1]
        else:
            username = raw_username.strip()
            initial_buffer = ""

        new_player_info = {
            "socket": conn,
            "username": username,
            "position": (0, 1, 0),
            "rotation": 0,
            "health": 100,
            "visible": True,
            "initial_buffer": initial_buffer
        }

        with players_lock:
            # Tell existing players about new player
            new_player_msg = (json.dumps({
                "id": new_id,
                "object": "player",
                "username": new_player_info["username"],
                "position": new_player_info["position"],
                "health": new_player_info["health"],
                "joined": True,
                "left": False
            }) + "\n").encode("utf8")

            for player_id, p_info in list(players.items()):
                try:
                    p_info["socket"].sendall(new_player_msg)
                except OSError:
                    pass

            # Tell new player about existing players
            for player_id, p_info in list(players.items()):
                existing_msg = (json.dumps({
                    "id": player_id,
                    "object": "player",
                    "username": p_info["username"],
                    "position": p_info["position"],
                    "rotation": p_info.get("rotation", 0),
                    "health": p_info["health"],
                    "joined": True,
                    "left": False
                }) + "\n").encode("utf8")
                try:
                    conn.sendall(existing_msg)
                except OSError:
                    pass

            players[new_id] = new_player_info

        msg_thread = threading.Thread(target=handle_messages, args=(new_id,), daemon=True)
        msg_thread.start()

        print(f"New connection from {addr}, assigned ID: {new_id} ({username})...")


if __name__ == "__main__":
    while True:
        try:
            main()
        except KeyboardInterrupt:
            print("Server stopped manually.")
            break
        except SystemExit:
            print("System exit triggered.")
            break
        except Exception as e:
            print(f"Server crashed with error: {e}")
            print("Restarting server in 5 seconds...\n")
            time.sleep(5)
        finally:
            s.close()

