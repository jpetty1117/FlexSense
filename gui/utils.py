"""
UI utility helpers for graph interaction customization.
"""

from PySide6.QtCore import Qt


def patch_axis_to_scale_on_drag(axis_item):
    """
    Patch a pyqtgraph AxisItem so that left-click drag SCALES (zooms)
    the axis instead of translating (panning) it.

    Scales around the view center to avoid translation drift.
    Double-click on axis to auto-range.
    """
    original_drag = axis_item.mouseDragEvent

    def _scale_on_drag(ev):
        vb = axis_item.linkedView()
        if vb is None:
            return

        if ev.button() == Qt.MouseButton.LeftButton:
            ev.accept()

            if ev.isFinish():
                return

            dif = ev.pos() - ev.lastPos()

            # Scale around the VIEW CENTER (not mouse pos) to prevent drift
            view_center = vb.viewRect().center()

            if axis_item.orientation in ('left', 'right'):
                s = 1.01 ** dif.y()
                vb.scaleBy(y=s, center=view_center)
            else:
                s = 1.01 ** (-dif.x())
                vb.scaleBy(x=s, center=view_center)
        else:
            original_drag(ev)

    axis_item.mouseDragEvent = _scale_on_drag

    # Double-click on axis → auto-range that axis
    original_dbl = axis_item.mouseDoubleClickEvent

    def _double_click_reset(ev):
        vb = axis_item.linkedView()
        if vb is not None:
            if axis_item.orientation in ('left', 'right'):
                vb.enableAutoRange(axis=1, enable=True)
                vb.enableAutoRange(axis=1, enable=False)
            else:
                vb.enableAutoRange(axis=0, enable=True)
                vb.enableAutoRange(axis=0, enable=False)
        ev.accept()

    axis_item.mouseDoubleClickEvent = _double_click_reset


def patch_all_axes(plot_item):
    """
    Patch all axes on a PlotItem so left-drag scales instead of translates.
    """
    for axis_name in ('left', 'right', 'bottom', 'top'):
        try:
            axis = plot_item.getAxis(axis_name)
            if axis is not None and axis.isVisible():
                patch_axis_to_scale_on_drag(axis)
        except Exception:
            pass
