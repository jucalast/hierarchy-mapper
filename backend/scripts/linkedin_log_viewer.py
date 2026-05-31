import redis
import json
import time
import sys
import os

# Ajusta o sys.path para garantir que o diretório backend possa ser importado se necessário
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_viewer():
    # Habilita suporte a cores ANSI no terminal Windows (Win10+)
    if os.name == 'nt':
        os.system("") 

    # Códigos ANSI para cores
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

    print(f"{BLUE}{BOLD}====================================================================={RESET}")
    print(f"{BLUE}{BOLD}              LINKB2B - HIERARCHYSCAN LOG TERMINAL{RESET}")
    print(f"{BLUE}{BOLD}====================================================================={RESET}")
    print(f"\n{CYAN}[INFO] Status: {YELLOW}Aguardando comandos do Front-end...{RESET}")
    print(f"{CYAN}[INFO] Este terminal exibirá em tempo real o processo de automação. {RESET}")
    print(f"{CYAN}[INFO] Não é necessária entrada de dados aqui.{RESET}")
    print(f"\n{BLUE}---------------------------------------------------------------------{RESET}")

    retry_count = 0
    while True:
        try:
            # Conexão com o Redis local
            r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            p = r.pubsub()
            p.subscribe('linkedin_scan_logs')
            
            if retry_count > 0:
                print(f"{GREEN}[INFO] Conectado ao Redis com sucesso!{RESET}")
                retry_count = 0

            # Loop de escuta de mensagens
            for message in p.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        msg = data.get('message', '')
                        
                        # Formatação condicional baseada no conteúdo do log
                        if "📊 [Progresso]" in msg:
                            print(f"{CYAN}{msg}{RESET}")
                        elif "🖱️ [Ação]" in msg:
                            print(f"{YELLOW}{msg}{RESET}")
                        elif "✅" in msg or "🎉" in msg or "Extraído" in msg:
                            print(f"{BOLD}{GREEN}{msg}{RESET}")
                        elif "⚠️" in msg or "Warning" in msg:
                            print(f"{YELLOW}{msg}{RESET}")
                        elif "❌" in msg or "Error" in msg:
                            print(f"{RED}{msg}{RESET}")
                        elif "🚀" in msg or "Iniciando" in msg:
                            print(f"{BOLD}{CYAN}{msg}{RESET}")
                        else:
                            print(msg)
                            
                    except Exception as e:
                        # Se não for JSON, imprime como string pura
                        if isinstance(message['data'], str):
                            print(message['data'])
                        else:
                            pass
                            
        except redis.ConnectionError:
            retry_count += 1
            if retry_count % 5 == 1:
                print(f"{RED}[ERRO] Redis não encontrado. Tentando reconectar...{RESET}")
            time.sleep(2)
        except Exception as e:
            print(f"{RED}[ERRO] Falha no Log Viewer: {e}{RESET}")
            time.sleep(5)

if __name__ == "__main__":
    # Garante suporte a UTF-8 no terminal
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
            
    try:
        run_viewer()
    except KeyboardInterrupt:
        print("\n[INFO] Log Viewer encerrado pelo usuário.")
