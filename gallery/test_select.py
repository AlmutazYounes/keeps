import subprocess
import unittest
from pathlib import Path


class SelectRangeTest(unittest.TestCase):
    def test_shift_range_follows_grid_order(self):
        html = (Path(__file__).parent / "static" / "index.html").read_text()
        start = html.index("function idsInRange")
        end = html.index("function markFromTile")
        script = html[start:end] + """
        const cases = [
          [idsInRange([1, 2, 3, 4, 5], 2, 4), [2, 3, 4]],
          [idsInRange([1, 2, 3, 4, 5], 5, 2), [2, 3, 4, 5]],
          [idsInRange([1, 2, 3], 9, 2), [2]],
        ];
        for (const [got, want] of cases) {
          if (JSON.stringify(got) !== JSON.stringify(want)) {
            console.log(JSON.stringify({ got, want }));
            process.exit(1);
          }
        }
        console.log("ok");
        """
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok", result.stdout)

    def test_home_header_splits_tabs_from_actions(self):
        html = (Path(__file__).parent / "static" / "index.html").read_text()
        self.assertIn('class="tabs"', html)
        self.assertIn('class="links"', html)
        self.assertIn('class="actions"', html)
        self.assertIn(".cell:hover .tick", html)
        self.assertIn("event.shiftKey", html)
        self.assertNotIn("\u2014", html)


if __name__ == "__main__":
    unittest.main()
