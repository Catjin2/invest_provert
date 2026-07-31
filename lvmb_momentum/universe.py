import os
import json
from datetime import datetime

class AntiGravityUniverse:
    def __init__(self):
        self.config_path = "invest_universe.json"

    def get_nasdaq100(self):
        """Returns the global multi-asset ETF universe."""
        return [
            "SPY", "QQQ", "IWM", "VGK", "EWJ", 
            "XLK", "XLF", "XLE", "XLV", 
            "GLD", "USO", "TLT", "IEF", "SHY", "LQD"
        ]

    def load_base_universe(self):
        """Loads the current base universe from disk, or fetches it if not present."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "nasdaq_100" in data:
                        return data["nasdaq_100"]
            except Exception:
                pass
        return self.get_nasdaq100()

    def get_universe_for_year(self, year):
        """Reconstructs the universe for a specific year (disabled for ETF universe)."""
        return list(self.load_base_universe())

    def update_universe(self):
        print("Updating Anti-Gravity Universe...")
        ndx = self.get_nasdaq100()
        
        universe = {
            "nasdaq_100": ndx,
            "last_updated": datetime.now().isoformat()
        }
        
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(universe, f, indent=4)
        
        return universe

    def load_universe(self, year=None):
        if year is not None:
            tickers = self.get_universe_for_year(year)
            return {
                "nasdaq_100": tickers,
                "year": year,
                "last_updated": datetime.now().isoformat()
            }
        if not os.path.exists(self.config_path):
            return self.update_universe()
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

if __name__ == "__main__":
    uni = AntiGravityUniverse()
    data = uni.update_universe()
    print(f"Universe Loaded: NDX({len(data['nasdaq_100'])})")
