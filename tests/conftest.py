"""The tests read the interface in French, its source language, whatever Windows speaks:
test_i18n.py checks the English one."""

import os

os.environ["LOCALCHORDS_LANG"] = "fr"
