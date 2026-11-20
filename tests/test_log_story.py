"""Hunter exploration must work without a network comparison or any repeat hunters."""
import unittest
from streamlit.testing.v1 import AppTest

APP = '''
import pandas as pd
import log_check as lc
from views.log_view import _story
log = lc.parse_adif("<CALL:5>W1AAA <QSO_DATE:8>20261118 <TIME_ON:4>1200 <BAND:3>20m <MODE:2>CW <EOR>"
                    "<CALL:5>W1AAA <QSO_DATE:8>20261118 <TIME_ON:4>1210 <BAND:3>15m <MODE:2>CW <EOR>"
                    "<CALL:5>W2BBB <QSO_DATE:8>20261118 <TIME_ON:4>1220 <BAND:3>20m <MODE:2>CW <EOR>")
_story(log, lc.summary(log), 'test', None)
'''

class LogStory(unittest.TestCase):
    def test_selection_and_empty_search_work_without_network(self):
        at = AppTest.from_string(APP).run()
        self.assertEqual(list(at.exception), [])
        at.selectbox[0].select('W1AAA').run()
        self.assertEqual(list(at.exception), [])
        self.assertTrue(any('W1AAA · 2 bands · 2 contacts' in m.value for m in at.markdown))
        at.text_input[0].input('no match').run()
        self.assertEqual(list(at.exception), [])
