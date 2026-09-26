"""The panel's photograph check needs the browser to open the picked file.

Before an upload starts, `panel.js` opens the chosen file through
`URL.createObjectURL` to read its size, so the owner never waits for an upload
the server would refuse. The policy of §17 #269 allowed images from this site
and from `data:` only. The browser refused the `blob:` address, the check read
the refusal as a broken file, and every photograph was turned away as "not an
image" from 25 September, when the policy went live, until this fix
(§17 #296). No test could see it: the check runs in a browser, and the policy
had been driven in one only on public pages.
"""
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from core.middleware import BASE_POLICY, MAPS_POLICY

from .test_phase7 import make_staff
from .test_phase10 import directives

JS = Path(settings.BASE_DIR) / 'static' / 'js'


class PanelImageCheckTests(TestCase):
    """The page that checks a photograph is allowed to look at it."""

    def test_the_product_editor_may_open_a_picked_file(self):
        self.client.force_login(make_staff())
        with translation.override('uz'):
            url = reverse('panel_product_new')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        policy = directives(response.headers['Content-Security-Policy'])
        self.assertIn('blob:', policy['img-src'])

    def test_a_script_that_makes_blob_addresses_has_them_allowed(self):
        """The rule rather than the one file: any script here that turns a
        file into a `blob:` address needs the policy to let it be shown. If
        none does any more, this says so, and the source can go.
        """
        users = [path.name for path in sorted(JS.glob('*.js'))
                 if 'createObjectURL' in path.read_text(encoding='utf-8')]
        self.assertTrue(users, 'no script opens a file any more - blob: can go')
        self.assertIn('blob:', BASE_POLICY['img-src'], users)

    def test_the_maps_additions_repeat_nothing_the_base_has(self):
        """The Maps policy is appended to this one, so a source in both would
        be sent twice on the checkout and in the admin."""
        for key, values in MAPS_POLICY.items():
            with self.subTest(directive=key):
                self.assertFalse(set(values) & set(BASE_POLICY.get(key, ())))
