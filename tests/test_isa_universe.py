import unittest
from lvmb_momentum.universe import ISAUniverse, AssetRole, ISATicker

class TestISAUniverse(unittest.TestCase):
    def test_isa_tickers_defined(self):
        symbols = ISAUniverse.get_all_symbols()
        self.assertIn("133690.KS", symbols)
        self.assertIn("446720.KS", symbols)
        self.assertIn("329650.KS", symbols)
        self.assertEqual(len(symbols), 5)

    def test_filter_by_role(self):
        growth = ISAUniverse.get_symbols_by_role(AssetRole.CORE_GROWTH)
        dividend = ISAUniverse.get_symbols_by_role(AssetRole.CORE_DIVIDEND)
        safe = ISAUniverse.get_symbols_by_role(AssetRole.SAFE_ASSET)

        self.assertIn("133690.KS", growth)
        self.assertIn("360750.KS", growth)
        self.assertIn("446720.KS", dividend)
        self.assertIn("402970.KS", dividend)
        self.assertIn("329650.KS", safe)

    def test_get_name_conversion(self):
        name_nasdaq = ISAUniverse.get_name("133690.KS")
        self.assertEqual(name_nasdaq, "TIGER 미국나스닥100")
        name_schd = ISAUniverse.get_name("446720.KS")
        self.assertEqual(name_schd, "SOL 미국배당다우존스")
        name_unknown = ISAUniverse.get_name("AAPL")
        self.assertEqual(name_unknown, "AAPL")

if __name__ == "__main__":
    unittest.main()
