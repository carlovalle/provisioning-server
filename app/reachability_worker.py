import os
import socket
import time
from datetime import datetime

from database import SessionLocal
from models import Switch

POLL_INTERVAL = int(os.getenv("REACH_POLL_INTERVAL", "10"))
CONNECT_TIMEOUT = float(os.getenv("REACH_CONNECT_TIMEOUT", "2"))
BATCH_SIZE = int(os.getenv("REACH_BATCH_SIZE", "50"))
PORT = int(os.getenv("REACH_PORT", "22"))


def can_reach_tcp(ip: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def main():
    print("[reachability_worker] up - polling switches...")
    while True:
        db = SessionLocal()
        try:
            # Trae switches con AL MENOS una IP (mgmt_ip o last_seen_ip)
            switches = (
                db.query(Switch)
                .filter(
                    (Switch.mgmt_ip.isnot(None)) |
                    (Switch.last_seen_ip.isnot(None))
                )
                .limit(BATCH_SIZE)
                .all()
            )

            for sw in switches:
                candidate_ips = []

                if sw.mgmt_ip and str(sw.mgmt_ip).strip():
                    candidate_ips.append(sw.mgmt_ip)

                if sw.last_seen_ip and str(sw.last_seen_ip).strip():
                    if sw.last_seen_ip not in candidate_ips:
                        candidate_ips.append(sw.last_seen_ip)

                if not candidate_ips:
                    continue

                reachable_ip = None
                for ip in candidate_ips:
                    if can_reach_tcp(ip, PORT, CONNECT_TIMEOUT):
                        reachable_ip = ip
                        break

                sw.last_reachability_check = datetime.utcnow()

                if reachable_ip:
                    if sw.reachable is False:
                        sw.reachable = True
                        print(f"[reachability_worker] {sw.serial_number} reachable=True via {reachable_ip}")

                    # Si la IP alcanzable es last_seen_ip, sincroniza mgmt_ip
                    if reachable_ip == sw.last_seen_ip and sw.mgmt_ip != sw.last_seen_ip:
                        sw.mgmt_ip = sw.last_seen_ip
                        print(f"[reachability_worker] {sw.serial_number} mgmt_ip updated to {sw.mgmt_ip}")

                else:
                    if sw.reachable is True:
                        sw.reachable = False
                        print(f"[reachability_worker] {sw.serial_number} reachable=False")

                db.commit()

        except Exception as e:
            db.rollback()
            print(f"[reachability_worker] ERROR: {e}")
        finally:
            db.close()

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()