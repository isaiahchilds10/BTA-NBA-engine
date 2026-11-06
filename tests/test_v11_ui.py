"""No network required. Validates UI integration without claiming deployed rendering."""
from __future__ import annotations
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class TestBTAV11UI(unittest.TestCase):
    def test_preserves_original(self):
        self.assertFalse((ROOT/'app.py').exists())  # bundle never replaces working app
        self.assertFalse((ROOT/'pages'/'01_BTA_Command_Center.py').exists())

    def test_shared_branding(self):
        logo=(ROOT/'bta_ui/assets/bta_belt.svg').read_text(encoding='utf-8')
        theme=(ROOT/'bta_ui/theme.py').read_text(encoding='utf-8')
        self.assertIn('BELT TO ASS',logo)
        self.assertIn('E4203C',theme)
        self.assertIn('@media(max-width:800px)',theme)
        self.assertIn('escape(',theme)

    def test_all_research_pages_present(self):
        for index in range(2,10):
            self.assertEqual(len(list((ROOT/'pages').glob(f'{index:02d}_*.py'))),1)

    def test_new_router_has_three_sports_and_legacy(self):
        router=(ROOT/'bta_ui_app.py').read_text(encoding='utf-8')
        self.assertIn('st.navigation',router)
        self.assertIn('pg.run()',router)
        self.assertIn('pages/01_BTA_Command_Center.py',router)
        self.assertIn('pages/09_BTA_Certification_Lab.py',router)
        for sport in ['NBA','NFL','CFB']:
            self.assertIn(f'"{sport}"',router)

    def test_source_files_parse(self):
        for file in [ROOT/'bta_ui_app.py',*(ROOT/'bta_ui').glob('*.py')]:
            ast.parse(file.read_text(encoding='utf-8'),filename=str(file))

    def test_no_fake_performance_percentages(self):
        home=(ROOT/'bta_ui/home.py').read_text(encoding='utf-8')
        self.assertIn('"N/A"',home)
        self.assertIn('"PENDING"',home)
        self.assertNotIn('98.7%',home)

if __name__ == '__main__': unittest.main()
