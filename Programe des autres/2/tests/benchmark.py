import os
import sys
import time
import subprocess
import tempfile
import statistics
from pathlib import Path
import matplotlib.pyplot as plt

# Import des helpers de tes tests existants
from test_reseau_non_ideal import UDPProxy, launch_server

PYTHON = sys.executable
CLIENT_SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'src', 'client.py')
BASE_PORT = 10000
NB_REPETITIONS = 3  # On fait la moyenne de 3 essais pour chaque point

def make_bench_file(tmp_path, size_bytes, name):
    path = tmp_path / name
    path.write_bytes(os.urandom(size_bytes))
    return path

def run_single_transfer(tmp_path, filename, port):
    """Exécute un seul transfert et retourne le temps mis (ou None si erreur)"""
    fichier_recu = tmp_path / f"recu_{time.time()}.bin"
    start = time.time()
    try:
        proc = subprocess.Popen(
            [PYTHON, CLIENT_SCRIPT, f"http://[::1]:{port}/{filename}", "--save", str(fichier_recu)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        proc.wait(timeout=60)
        if proc.returncode == 0:
            return time.time() - start
    except Exception:
        pass
    return None

def run_test_case(tmp_path, size_mb, loss, delay, port_base):
    """Lance plusieurs répétitions pour une condition donnée et fait la moyenne"""
    filename = f"file_{size_mb}MB.bin"
    make_bench_file(tmp_path, int(size_mb * 1024 * 1024), filename)
    
    times = []
    for i in range(NB_REPETITIONS):
        srv = launch_server(tmp_path, port=port_base)
        proxy = UDPProxy(proxy_port=port_base+1, server_port=port_base, loss_rate=loss, delay_range=(delay, delay))
        proxy.start()
        
        duration = run_single_transfer(tmp_path, filename, port_base+1)
        
        proxy.stop()
        srv.terminate()
        srv.wait()
        
        if duration:
            times.append(duration)
            
    if not times: return 0
    avg_time = statistics.mean(times)
    return size_mb / avg_time # Retourne le débit en Mo/s

# ============================================================
# LES DIFFÉRENTES CAMPAGNES DE TESTS
# ============================================================

def test_latence(tmp_path):
    print("\n--- TEST 1 : IMPACT DE LA LATENCE (Pertes=0%, 1Mo) ---")
    delays = [0, 20, 50, 100, 200]
    results = []
    for d in delays:
        tp = run_test_case(tmp_path, 1.0, 0.0, d, BASE_PORT)
        results.append(tp)
        print(f"  Latence {d}ms -> {tp:.3f} Mo/s")
    return delays, results

def test_pertes(tmp_path):
    print("\n--- TEST 2 : IMPACT DES PERTES (Latence=10ms, 1Mo) ---")
    losses = [0.0, 0.02, 0.05, 0.1, 0.2]
    results = []
    for l in losses:
        tp = run_test_case(tmp_path, 1.0, l, 10, BASE_PORT + 10)
        results.append(tp)
        print(f"  Pertes {l*100}% -> {tp:.3f} Mo/s")
    return [l*100 for l in losses], results

def test_tailles(tmp_path):
    print("\n--- TEST 3 : IMPACT DE LA TAILLE (Réseau Idéal) ---")
    sizes = [0.1, 0.5, 1.0, 5.0, 10.0]
    results = []
    for s in sizes:
        tp = run_test_case(tmp_path, s, 0.0, 0, BASE_PORT + 20)
        results.append(tp)
        print(f"  Taille {s}Mo -> {tp:.3f} Mo/s")
    return sizes, results

def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Exécution des tests séparés
        x1, y1 = test_latence(tmp_path)
        x2, y2 = test_pertes(tmp_path)
        x3, y3 = test_tailles(tmp_path)
        
        # Génération du rapport visuel
        fig, axs = plt.subplots(1, 3, figsize=(18, 5))
        
        axs[0].plot(x1, y1, 'b-o'); axs[0].set_title('Débit vs Latence (ms)'); axs[0].grid(True)
        axs[1].plot(x2, y2, 'r-o'); axs[1].set_title('Débit vs Pertes (%)'); axs[1].grid(True)
        axs[2].plot(x3, y3, 'g-o'); axs[2].set_title('Débit vs Taille Fichier (Mo)'); axs[2].grid(True)
        
        plt.tight_layout()
        plt.savefig('rapport_performances.png')
        print("\nBenchmark terminé. Graphiques sauvegardés dans 'rapport_performances.png'")

if __name__ == "__main__":
    main()