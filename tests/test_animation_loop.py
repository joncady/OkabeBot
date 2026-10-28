"""Exercise the real frame scheduler without importing Tk/AIY on the test host."""

import ast
from pathlib import Path
from types import SimpleNamespace, MethodType
import time
import unittest
from unittest.mock import Mock, patch


class AnimationLoopTests(unittest.TestCase):
    def test_transient_frame_failure_keeps_scheduling_and_recovers(self):
        source = Path(__file__).parents[1] / "pi/service.py"
        tree = ast.parse(source.read_text())
        display = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Display")
        method = next(
            n for n in display.body if isinstance(n, ast.FunctionDef) and n.name == "animate"
        )
        namespace = {"time": time}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
        fake = SimpleNamespace(
            animate_frame=Mock(side_effect=ValueError("transient canvas failure")), root=Mock()
        )
        fake.animate = MethodType(namespace["animate"], fake)
        with patch("traceback.print_exc"):
            fake.animate()
        self.assertIn("transient canvas failure", fake.animation_error)
        self.assertEqual(fake.root.after.call_args.args[1], fake.animate)
        fake.animate_frame.side_effect = None
        fake.animate()
        self.assertIsNone(fake.animation_error)
        self.assertEqual(fake.root.after.call_count, 2)

    def test_notification_rebinds_tk_image_before_releasing_previous(self):
        import base64
        import io

        tree = ast.parse((Path(__file__).parents[1] / "pi/service.py").read_text())
        display = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Display")
        method = next(
            n
            for n in display.body
            if isinstance(n, ast.FunctionDef) and n.name == "set_notification"
        )
        old, new = object(), object()
        scene = Mock()
        scene.card.return_value.resize.return_value.save.side_effect = lambda buf, **kw: buf.write(
            b"png"
        )
        namespace = {
            "time": time,
            "io": io,
            "base64": base64,
            "tk": Mock(PhotoImage=Mock(return_value=new)),
            "scene": scene,
            "Image": SimpleNamespace(NEAREST=0),
        }
        exec(compile(ast.Module(body=[method], type_ignores=[]), "service.py", "exec"), namespace)
        fake = SimpleNamespace(
            character={},
            card_photo=old,
            notification_item=42,
            canvas=Mock(),
            root=Mock(),
            status=Mock(),
        )
        fake.root.winfo_screenwidth.return_value, fake.root.winfo_screenheight.return_value = (
            480,
            320,
        )

        def rebind(*args, **kwargs):
            self.assertIs(fake.card_photo, old)
            self.assertIs(kwargs["image"], new)

        fake.canvas.itemconfigure.side_effect = rebind
        namespace["set_notification"](fake, {"notification": None})
        fake.canvas.itemconfigure.assert_called_once()
        self.assertIs(fake.card_photo, new)
