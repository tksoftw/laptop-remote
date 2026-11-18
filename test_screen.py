import io
import unittest

from PIL import Image, ImageDraw

from screen import encode_frame


class FrameTests(unittest.TestCase):
    def test_zoom_and_pan_select_actual_pixels(self):
        with Image.new('RGB', (1600, 900), 'red') as source:
            ImageDraw.Draw(source).rectangle((800, 0, 1599, 899), fill='blue')
            for view, channel in [((0, 0.5, 2), 0), ((1, 0.5, 2), 2)]:
                data, width, height = encode_frame(source, view)
                self.assertEqual((width, height), (1600, 900))
                with Image.open(io.BytesIO(data)) as decoded:
                    self.assertEqual(decoded.size, (800, 450))
                    self.assertGreater(decoded.getpixel((400, 225))[channel], 250)

    def test_full_display_preserves_aspect_and_bounds_frame_size(self):
        with Image.new('RGB', (3840, 2160)) as source:
            data, width, height = encode_frame(source, (0.5, 0.5, 1))
            self.assertEqual((width, height), source.size)
            with Image.open(io.BytesIO(data)) as decoded:
                self.assertEqual(decoded.size, (1280, 720))


if __name__ == '__main__':
    unittest.main()
