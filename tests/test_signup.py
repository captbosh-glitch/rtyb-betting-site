"""
signup.fill: Beehiiv shows a given form once per page, so a second spot
with the same form ID becomes a link to the first.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import signup  # noqa: E402


class Fill(unittest.TestCase):
    def setUp(self):
        self.old = dict(signup.FORMS)

    def tearDown(self):
        signup.FORMS.clear()
        signup.FORMS.update(self.old)

    def test_one_form_per_page(self):
        signup.FORMS.update(tab='A', footer='A')
        out = signup.fill('<main>' + signup.box('tab') + '</main><footer>' + signup.box('footer') + '</footer>')
        self.assertEqual(out.count('data-beehiiv-form="A"'), 1)
        self.assertIn('id="signup-tab"', out)
        self.assertIn('href="#signup-tab"', out.split('<footer>')[1])

    def test_footer_alone_gets_the_form(self):
        signup.FORMS.update(tab='A', footer='A')
        out = signup.fill('<footer>' + signup.box('footer') + '</footer>')
        self.assertIn('id="signup-footer"', out)

    def test_separate_forms_both_show(self):
        signup.FORMS.update(tab='A', footer='B')
        out = signup.fill(signup.box('tab') + signup.box('footer'))
        self.assertIn('data-beehiiv-form="A"', out)
        self.assertIn('data-beehiiv-form="B"', out)


if __name__ == '__main__':
    unittest.main()
