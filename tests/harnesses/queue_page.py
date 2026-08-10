"""AppTest entry point for the work-orders page.

``st.navigation`` builds its pages from callables, and AppTest.switch_page can
only resolve file-backed pages, so the second destination is unreachable from
the main script in a test. Rendering the page directly here tests the same
function the navigation runs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from data_layer.work_orders import init_db
from ui import pages

init_db()
pages.queue_page()
