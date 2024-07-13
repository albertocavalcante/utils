import winreg

def chrome_version():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Google\Chrome\BLBeacon')
        version, _ = winreg.QueryValueEx(key, 'version')
        winreg.CloseKey(key)
        return version
    except FileNotFoundError:
        return "Chrome version not found in the registry."
    except Exception as e:
        return f"An error occurred: {e}"


if __name__ == "__main__":
    chrome_version = chrome_version()
    print("Chrome version:", chrome_version)
