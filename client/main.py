import os
import sys
import time
import socket
import threading
import queue
import ursina
from network import Network
from floor import Floor
from map import Map
import random
from player import Player
from enemy import Enemy, COLOR_NAMES, COLOR_PALETTE
from bullet import Bullet
import tkinter as tk
from tkinter import font, ttk
from PIL import Image, ImageTk
import psutil
import pygame

PORT = 8888 # this port is what you get from playit.gg dashboard

def get_connected_devices():
    ip_addresses = []
    for conn in psutil.net_connections(kind='inet'):
        if conn.raddr and conn.laddr.ip.startswith('192.168.0.'):
            ip_addresses.append(conn.raddr.ip)
    return list(set(ip_addresses))

def get_user_input():
    root = tk.Tk()
    root.attributes('-fullscreen', True)
    # root.geometry("800x600")  # You can start with a default size
    # root.resizable(True, True)  # Make the window resizable

    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # Load and resize the background image
    bg_image = Image.open("assets/background.jpg")
    bg_image = bg_image.resize((screen_width, screen_height), Image.LANCZOS)
    bg_photo = ImageTk.PhotoImage(bg_image)

    # Create a canvas to hold the background image
    canvas = tk.Canvas(root, width=screen_width, height=screen_height)
    canvas.pack(fill='both', expand=True)
    canvas.create_image(0, 0, image=bg_photo, anchor='nw')

    custom_font = font.Font(family="Helvetica", size=28, weight="bold")
    input_font = font.Font(family="Arial", size=20, weight="normal")
    title_font = font.Font(family="Helvetica", size=35, weight="bold")

    frame = tk.Frame(root, bg='#010d25')
    canvas.create_window(screen_width // 2, screen_height // 2, window=frame, anchor='center')

    username_label = tk.Label(frame, text="Enter your username:", font=custom_font, fg='lightblue', bg='#010d25')
    username_label.pack(pady=20)

    default_color_name = random.choice(COLOR_NAMES)
    username_var = tk.StringVar(value=default_color_name)
    username_entry = ttk.Combobox(frame, textvariable=username_var, values=COLOR_NAMES, font=input_font, width=25, justify='center')
    username_entry.pack(pady=(10, 5))

    color_indicator = tk.Label(frame, text="", font=("Arial", 12, "bold"), bg='#010d25')
    color_indicator.pack(pady=(0, 10))

    def update_color_indicator(*args):
        val = username_var.get().strip().title()
        if val in COLOR_PALETTE:
            rgb = COLOR_PALETTE[val]
            hex_color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            color_indicator.config(text=f"● Player Color: {val}", fg=hex_color)
        else:
            found = False
            for cname, rgb in COLOR_PALETTE.items():
                if cname.lower() in val.lower():
                    hex_color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
                    color_indicator.config(text=f"● Player Color: {cname}", fg=hex_color)
                    found = True
                    break
            if not found:
                color_indicator.config(text="● Custom Username", fg='lightblue')

    username_var.trace_add("write", update_color_indicator)
    update_color_indicator()

    # Server IP
    server_label = tk.Label(frame, text="Enter server address:", font=custom_font, fg='lightblue', bg='#010d25')
    server_label.pack(pady=(20, 10))

    server_var = tk.StringVar(value="192.168.0.103")
    ip_addresses = get_connected_devices()
    server_combobox = ttk.Combobox(frame, textvariable=server_var, values=ip_addresses, font=input_font, width=25, justify='center')
    server_combobox.pack(pady=(0, 20))

    # Server Port
    port_label = tk.Label(frame, text="Enter port number:", font=custom_font, fg='lightblue', bg='#010d25')
    port_label.pack(pady=(0, 10))

    port_var = tk.StringVar(value=PORT)
    port_entry = tk.Entry(frame, textvariable=port_var, font=input_font, width=25, justify='center')
    port_entry.pack(pady=(0, 30))

    server_combobox.focus_set()
    server_combobox.icursor(tk.END)

    def on_ok():
        root.destroy()

    def on_close():
        root.destroy()
        exit()

    ok_button = tk.Button(frame, text="Play", command=on_ok, font=input_font, bg='green', fg='white')
    ok_button.pack(side=tk.RIGHT, padx=10)

    close_button = tk.Button(frame, text="Close", command=on_close, font=input_font, bg='red', fg='white')
    close_button.pack(side=tk.LEFT, padx=10)

    root.bind('<Return>', lambda event: on_ok())
    root.bind('<Escape>', lambda event: on_close())
    
    try:
        pygame.mixer.init()
        pygame.mixer.music.load("assets/music.mp3")
        pygame.mixer.music.play(-1)
    except pygame.error as e:
        print(f"[WARNING] Audio initialization failed: {e}")

    root.mainloop()
    username = username_var.get()
    server_addr = server_var.get()
    return username, server_addr, int(port_var.get())

username, server_addr, server_port = get_user_input()

while True:
    try:
        server_port = int(server_port)
    except ValueError:
        print("\nThe port you entered was not a number, try again with a valid port...")
        continue

    n = Network(server_addr, server_port, username)
    n.settimeout(5)
    error_occurred = False

    try:
        n.connect()
    except ConnectionRefusedError:
        print("\nConnection refused! This can be because server hasn't started or has reached it's player limit.")
        error_occurred = True
    except socket.timeout:
        print("\nServer took too long to respond, please try again...")
        error_occurred = True
    except socket.gaierror:
        print("\nThe IP address you entered is invalid, please try again with a valid address...")
        error_occurred = True
    finally:
        n.settimeout(None)

    if not error_occurred:
        break

app = ursina.Ursina(
    fullscreen=True,
)

if hasattr(ursina.window, 'borderless'):
    ursina.window.borderless = False
if hasattr(ursina.window, 'title'):
    ursina.window.title = "Ursina FPS"
if hasattr(ursina.window, 'exit_button') and ursina.window.exit_button:
    ursina.window.exit_button.enabled = False

floor = Floor()
map = Map()
sky = ursina.Entity(
    model="sphere",
    texture=os.path.join("assets", "sky.png"),
    scale=9999,
    double_sided=True
)

player = Player(ursina.Vec3(0, 1, 0), n)
prev_pos = ursina.Vec3(player.world_position)
prev_dir = player.world_rotation_y
enemies = []
msg_queue = queue.Queue()
network_tick_rate = 1.0 / 30.0  # 30 updates per second
last_network_send_time = 0.0

def receive():
    while n.running:
        try:
            info = n.receive_info()
        except Exception as e:
            print(f"[Network] Receive error: {e}")
            continue

        if not info:
            if n.running:
                print("Server has stopped! Exiting...")
                msg_queue.put(None)
            break

        msg_queue.put(info)


def handle_server_info(info):
    if not isinstance(info, dict):
        return

    obj_type = info.get("object")
    if obj_type == "player":
        enemy_id = str(info.get("id"))
        if enemy_id == str(n.id):
            return

        enemy = None
        for e in enemies:
            if str(e.id) == enemy_id:
                enemy = e
                break

        if info.get("left"):
            if enemy:
                enemies.remove(enemy)
                enemy.cleanup()
                try:
                    ursina.destroy(enemy)
                except Exception:
                    pass
            return

        if not enemy:
            username = info.get("username", f"Player {enemy_id}")
            pos = ursina.Vec3(*info["position"]) if "position" in info else ursina.Vec3(0, 1, 0)
            new_enemy = Enemy(pos, enemy_id, username)
            new_enemy.health = info.get("health", 100)
            enemies.append(new_enemy)
            return

        if "position" in info:
            enemy.world_position = ursina.Vec3(*info["position"])
        if "rotation" in info:
            enemy.rotation_y = info["rotation"]

        new_health = info.get("health", enemy.health)
        if enemy.health <= 0 and new_health > 0:
            enemy.respawn(enemy.world_position, new_health)
        else:
            enemy.health = new_health

    elif obj_type in ("player_respawn", "respawn"):
        enemy_id = str(info.get("id"))
        if enemy_id == str(n.id):
            return

        enemy = None
        for e in enemies:
            if str(e.id) == enemy_id:
                enemy = e
                break

        if enemy:
            pos = ursina.Vec3(*info["position"]) if "position" in info else ursina.Vec3(0, 1, 0)
            health = info.get("health", 100)
            enemy.respawn(pos, health)

    elif obj_type == "bullet":
        b_pos = ursina.Vec3(*info["position"])
        b_dir = info["direction"]
        b_x_dir = info["x_direction"]
        b_damage = info.get("damage", 10)
        Bullet(b_pos, b_dir, b_x_dir, n, b_damage, slave=True)

    elif obj_type == "health_update":
        enemy_id = str(info.get("id"))
        if enemy_id == str(n.id):
            player.health = info["health"]
        else:
            for e in enemies:
                if str(e.id) == enemy_id:
                    e.health = info["health"]
                    break


def update():
    global last_network_send_time, prev_pos, prev_dir

    if ursina.held_keys['escape']:
        n.close()
        exit()

    while not msg_queue.empty():
        try:
            info = msg_queue.get_nowait()
        except queue.Empty:
            break

        if info is None:
            n.close()
            ursina.application.quit()
            return

        handle_server_info(info)

    if player.health > 0:
        current_time = time.time()
        if (current_time - last_network_send_time) >= network_tick_rate:
            pos_diff = (player.world_position - prev_pos).length()
            rot_diff = abs(player.world_rotation_y - prev_dir)
            if pos_diff > 0.01 or rot_diff > 0.5:
                n.send_player(player)
                prev_pos = ursina.Vec3(player.world_position)
                prev_dir = player.world_rotation_y
                last_network_send_time = current_time

def input(key):
    if player.health <= 0:
        if key in ("r", "space", "enter"):
            player.respawn()
        return

    if key == "left mouse down" and player.health > 0:
        b_pos = player.position + ursina.Vec3(0, 2, 0)
        bullet = Bullet(b_pos, player.world_rotation_y, -player.camera_pivot.world_rotation_x, n, ignore_entity=player)
        n.send_bullet(bullet)
        try:
            player.gun_sound.play()
        except Exception:
            pass


def main():
    msg_thread = threading.Thread(target=receive, daemon=True)
    msg_thread.start()
    app.run()

if __name__ == "__main__":
    main()
