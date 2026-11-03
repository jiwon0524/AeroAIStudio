from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class GridView(QWidget):
    cell_clicked = Signal(int, int)
    def __init__(self):
        super().__init__()
        self.snapshot: dict = {}
        self.editable = False
        self.setMinimumSize(320, 320)

    def set_state(self, snapshot: dict) -> None:
        self.snapshot = snapshot
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101923"))
        if not self.snapshot:
            p.setPen(QColor("#8ca0b5"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Save a scenario or select an episode")
            return
        s = self.snapshot
        w, h = s["width"], s["height"]
        size = min((self.width() - 30) / w, (self.height() - 30) / h)
        ox, oy = (self.width() - size * w) / 2, (self.height() - size * h) / 2
        obstacles = {tuple(v) for v in s["obstacles"]}
        danger = {tuple(v) for v in s.get('danger_zones', [])}
        slow = {tuple(v) for v in s.get('slow_zones', [])}
        moving = {tuple(v['position']) for v in s.get('dynamic_objects', [])}
        for x in range(w):
            for y in range(h):
                color = "#e19c54" if (x, y) in moving else "#8c3f59" if (x, y) in danger else "#665c37" if (x, y) in slow else "#405266" if (x, y) in obstacles else "#182735"
                p.fillRect(QRectF(ox + x * size + 1, oy + y * size + 1, size - 1, size - 1), QColor(color))
        for key, color, label in (("goal", "#45c996", "G"), ("agent", "#64b5ff", "A")):
            x, y = s[key]
            cell = QRectF(ox + x * size, oy + y * size, size, size)
            p.fillRect(cell.adjusted(1, 1, -1, -1), QColor(color))
            if size >= 15:
                p.setPen(QColor("#08111a"))
                p.drawText(cell, Qt.AlignmentFlag.AlignCenter, label)
        if "new_state" in s:
            x, y = s["new_state"]
            p.setPen(QPen(QColor("#ffce70"), 2))
            p.drawRect(QRectF(ox + x * size + 2, oy + y * size + 2, size - 4, size - 4))

    def mousePressEvent(self, event) -> None:
        if self.editable and self.snapshot and event.button() == Qt.MouseButton.LeftButton:
            w, h = self.snapshot['width'], self.snapshot['height']
            size = min((self.width() - 30) / w, (self.height() - 30) / h)
            x = int((event.position().x() - (self.width() - size * w) / 2) // size)
            y = int((event.position().y() - (self.height() - size * h) / 2) // size)
            if 0 <= x < w and 0 <= y < h:
                self.cell_clicked.emit(x, y)


class TrajectoryView(GridView):
    def __init__(self):
        super().__init__()
        self.path=[]
        self.collision_point=None
        self.cursor=0

    def set_episode(self,episode):
        from aero_ai_studio.replay.trajectory import trajectory
        data=trajectory(episode)
        self.path=data['points']
        self.collision_point=data['collision_point']
        self.set_state({'width':data['width'],'height':data['height'],'agent':data['points'][0],
                        'goal':data['goal'],'obstacles':data['obstacles']} if data['points'] else {})

    def paintEvent(self,event):
        super().paintEvent(event)
        if not self.path:return
        p=QPainter(self)
        w,h=self.snapshot['width'],self.snapshot['height']
        size=min((self.width()-30)/w,(self.height()-30)/h)
        ox,oy=(self.width()-size*w)/2,(self.height()-size*h)/2
        def point(v):return QPointF(ox+(v[0]+.5)*size,oy+(v[1]+.5)*size)
        p.setPen(QPen(QColor('#ffce70'),2))
        for a,b in zip(self.path,self.path[1:]):p.drawLine(point(a),point(b))
        if self.collision_point:
            p.setPen(QPen(QColor('#ff5555'),4))
            p.drawEllipse(point(self.collision_point),5,5)
        p.setPen(QPen(QColor('#64b5ff'),3))
        p.drawEllipse(point(self.path[min(self.cursor,len(self.path)-1)]),4,4)


class RewardChart(QWidget):
    def __init__(self):
        super().__init__()
        self.rows: list[dict] = []
        self.setMinimumHeight(180)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#101923"))
        p.setPen(QColor("#9fb0c2"))
        p.drawText(12, 22, "Reward per episode · blue    |    cumulative success rate · green (0–100%)")
        if len(self.rows) < 2:
            return
        left, top, width, height = 50, 38, self.width() - 65, self.height() - 58
        rewards = [r["reward"] for r in self.rows]
        lo, hi = min(rewards), max(rewards)
        p.drawText(4, top + 10, f"{hi:.0f}")
        p.drawText(4, top + height, f"{lo:.0f}")
        for values, color, low, high in ((rewards, "#64b5ff", lo, max(lo + 1, hi)),
                                        ([r["success_rate"] for r in self.rows], "#45c996", 0, 1)):
            p.setPen(QPen(QColor(color), 1.2))
            previous = None
            for i, value in enumerate(values):
                point = QPointF(left + width * i / (len(values) - 1), top + height * (1 - (value - low) / (high - low)))
                if previous is not None:
                    p.drawLine(previous, point)
                previous = point


class BrainMapView(QWidget):
    """A flow of measured decision data with Q-score bars, not hidden thoughts."""
    def __init__(self):
        super().__init__()
        self.step: dict = {}
        self.setMinimumSize(850, 240)

    def set_step(self, step: dict) -> None:
        self.step = step
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#101923"))
        if not self.step:
            p.setPen(QColor("#9fb0c2"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Select an episode in Replay to inspect recorded decisions")
            return
        s = self.step
        gap, margin = 24, 12
        width = (self.width() - margin * 2 - gap * 3) / 4
        titles = ("CURRENT STATE", "ACTION SCORES", "SELECTED ACTION", "RESULT")
        boxes = []
        for i, title in enumerate(titles):
            box = QRectF(margin + i * (width + gap), 18, width, self.height() - 36)
            boxes.append(box)
            p.setPen(QPen(QColor("#35546c"), 1))
            p.setBrush(QColor("#192a39"))
            p.drawRoundedRect(box, 5, 5)
            p.setPen(QColor("#74beff"))
            p.drawText(box.adjusted(10, 10, -6, -6), Qt.AlignmentFlag.AlignTop, title)
            if i < 3:
                y = box.center().y()
                x = box.right()
                p.setPen(QPen(QColor("#6587a3"), 2))
                p.drawLine(QPointF(x + 3, y), QPointF(x + gap - 3, y))
                p.drawLine(QPointF(x + gap - 8, y - 5), QPointF(x + gap - 3, y))
                p.drawLine(QPointF(x + gap - 8, y + 5), QPointF(x + gap - 3, y))
        texts = {
            0: f"Position {s['state']}\n\nGoal {s['goal']}\n\nObstacles {len(s['obstacles'])}",
            2: f"{s['selected_action'].upper()}\n\n{'Exploration' if s['exploring'] else 'Exploitation'}\n\nEpsilon {s['epsilon']:.4f}",
            3: f"Reward {s['reward']:+.1f}\n\nNew state {s['new_state']}\n\n{s['reason'].upper()}"}
        p.setPen(QColor("#dce7f3"))
        for i, text in texts.items():
            p.drawText(boxes[i].adjusted(10, 48, -8, -8), Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, text)
        best = max(s["q_values"].values())
        scale = max(1, max(abs(v) for v in s["q_values"].values()))
        box = boxes[1]
        for i, (action, value) in enumerate(s["q_values"].items()):
            y = box.top() + 46 + i * 33
            color = QColor("#45c996" if value == best else "#64b5ff")
            if action == s["selected_action"]:
                p.fillRect(QRectF(box.left() + 6, y - 2, box.width() - 12, 30), QColor("#284761"))
            p.setPen(color)
            info = s.get('action_evidence', {}).get(action)
            suffix = '' if not info else (' · valid' if info['valid'] else ' · INVALID')
            p.drawText(QRectF(box.left() + 10, y, box.width() - 20, 18), f"{action.upper()}  {value:+.3f}{suffix}")
            p.fillRect(QRectF(box.left() + 10, y + 21, (box.width() - 20) * abs(value) / scale, 3), color)


class ComparisonChart(QWidget):
    def __init__(self):
        super().__init__()
        self.runs: list[dict] = []
        self.setMinimumSize(700, 300)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#101923'))
        colors = ['#64b5ff', '#45c996', '#ffce70', '#e783c8', '#ad9fff']
        all_rewards = [r['reward'] for run in self.runs for r in run['series']]
        lo, hi = min(all_rewards, default=0), max(all_rewards, default=1)
        max_episode = max((len(run['series']) for run in self.runs), default=1)
        for panel, (metric, low, high, title) in enumerate((('success_rate', 0, 1, 'Cumulative training success (0–100%)'),
                                                          ('reward', lo, max(lo + 1, hi), f'Reward ({lo:.0f} … {hi:.0f})'))):
            left, top = 55, 30 + panel * self.height() / 2
            width, height = self.width() - 75, self.height() / 2 - 55
            p.setPen(QColor('#bacadb'))
            p.drawText(int(left), int(top - 10), title)
            for index, run in enumerate(self.runs):
                p.setPen(QPen(QColor(colors[index % len(colors)]), 1.1))
                previous = None
                series = run['series']
                stride = max(1, len(series) // 1000)
                for row in series[::stride]:
                    point = QPointF(left + width * row['episode'] / max(1, max_episode), top + height * (1 - (row[metric] - low) / (high - low)))
                    if previous:
                        p.drawLine(previous, point)
                    previous = point
