from netmiko import ConnectHandler

def get_switch_info(public_ip, port=2222, username="carlovalle", password="M@iden10291990"):
    device = {
        "device_type": "cisco_ios",
        "host": public_ip,
        "username": username,
        "password": password,
        "port": port,
    }

    try:
        conn = ConnectHandler(**device)
        show_ver = conn.send_command("show version")
        show_inv = conn.send_command("show inventory")
        conn.disconnect()

        return {
            "show_version": show_ver,
            "show_inventory": show_inv
        }

    except Exception as e:
        return {"error": str(e)}