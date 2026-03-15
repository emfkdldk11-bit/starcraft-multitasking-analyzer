import sys
import os
import json
import subprocess
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                             QLabel, QTextEdit, QMessageBox)
from PyQt6.QtCore import Qt

# 1. 경로 해결 함수 (PyInstaller용)
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# 2. 분석 로직 함수
def analyze_replay_data(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    players = {p['ID']: p['Name'] for p in data['Header']['Players']}
    p0_name = players.get(0, "Player 0")
    p1_name = players.get(1, "Player 1")

    raw_cmds = data.get('Commands', {}).get('Cmds', [])
    df = pd.DataFrame([{
        'frame': c.get('Frame', 0),
        'player_id': c.get('PlayerID', 0),
        'name': c.get('Type', {}).get('Name', 'Unknown')
    } for c in raw_cmds])

    def get_metrics(player_df):
        p_df = player_df.copy()
        if p_df.empty: return None
        p_df['minute'] = p_df['frame'] // 1428
        p_df['is_spam'] = (p_df['name'] == p_df['name'].shift(1)) & ((p_df['frame'] - p_df['frame'].shift(1)) <= 10)
        
        apm = p_df.groupby('minute').size()
        eapm = p_df[~p_df['is_spam']].groupby('minute').size()
        macro = p_df[p_df['name'].str.contains('Hotkey|Train|Build|Tech|Upgrade', na=False)].groupby('minute').size()
        micro = p_df[p_df['name'] == 'Targeted Order'].groupby('minute').size()
        mt_score = np.sqrt((micro + 1) * (macro + 1))
        return {"apm": apm, "eapm": eapm, "macro": macro, "micro": micro, "mt": mt_score}

    m0 = get_metrics(df[df['player_id'] == 0])
    m1 = get_metrics(df[df['player_id'] == 1])

    plt.style.use('dark_background')
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 12), sharex=True)

    # 그래프 그리기 로직 (EAPM / Mechanics / Multitasking)
    if m1: 
        ax1.plot(m1['eapm'].index, m1['eapm'].values, color='#FF3333', label=f'{p1_name} (EAPM)', lw=2)
        ax2.plot(m1['macro'].index, m1['macro'].values, color='#FFA500', label='My Macro')
        ax2.plot(m1['micro'].index, m1['micro'].values, color='#00FFFF', label='My Micro')
        ax3.fill_between(m1['mt'].index, 0, m1['mt'].values, color='#FF3333', alpha=0.2, label='My Intensity')
    if m0: 
        ax1.plot(m0['eapm'].index, m0['eapm'].values, color='#3399FF', label=f'{p0_name} (EAPM)', lw=2)
        ax2.plot(m0['macro'].index, m0['macro'].values, color='#FFA500', alpha=0.3, ls='--')
        ax2.plot(m0['micro'].index, m0['micro'].values, color='#00FFFF', alpha=0.3, ls='--')
        ax3.plot(m0['mt'].index, m0['mt'].values, color='#3399FF', ls=':', label='Opponent Intensity')

    ax1.set_title('Indicator 1: Real Action Speed (EAPM)')
    ax2.set_title('Indicator 2: Mechanics (Macro & Micro)')
    ax3.set_title('Indicator 3: Multitasking Intensity Score')
    for ax in [ax1, ax2, ax3]: ax.legend(loc='upper right')
    plt.tight_layout()
    
    report = f"--- 분석 요약 ---\n"
    if m1 and m0:
        report += f"[{p1_name}] EAPM: {int(m1['eapm'].mean())} | MT Score: {m1['mt'].mean():.1f}\n"
        report += f"[{p0_name}] EAPM: {int(m0['eapm'].mean())} | MT Score: {m0['mt'].mean():.1f}\n"
    return fig, report

# 3. GUI 클래스
class StarAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('StarCraft Multitasking Analyzer v1.0')
        self.setFixedSize(600, 450)
        self.setAcceptDrops(True)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.label = QLabel('\n\n리플레이(.rep) 파일을\n여기로 드래그하세요\n\n', self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("border: 3px dashed #666; border-radius: 15px; font-size: 18px; color: #aaa; background-color: #222;")
        self.result_text = QTextEdit()
        self.result_text.setStyleSheet("background-color: #111; color: #0f0; font-family: Consolas;")
        self.result_text.setReadOnly(True)
        layout.addWidget(self.label)
        layout.addWidget(self.result_text)
        c = QWidget(); c.setLayout(layout); self.setCentralWidget(c)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()
        else: e.ignore()

    def dropEvent(self, e):
        file_path = e.mimeData().urls()[0].toLocalFile()
        if file_path.lower().endswith('.rep'): self.process_file(file_path)
        else: QMessageBox.warning(self, "파일 오류", ".rep 파일만 분석 가능합니다!")

    def process_file(self, rep_path):
        self.result_text.setText("분석 중... 잠시만 기다려 주세요.")
        json_temp = "temp_replay.json"
        try:
            # [핵심] 실행 시점에 screp.exe의 경로를 찾음
            screp_bin = resource_path("screp.exe")
            cmd = f'"{screp_bin}" -cmds "{rep_path}"'
            
            with open(json_temp, "w", encoding="utf-8") as f:
                subprocess.run(cmd, stdout=f, shell=True, check=True)
            
            fig, report = analyze_replay_data(json_temp)
            self.result_text.setText(report)
            plt.show()
        except Exception as e:
            self.result_text.setText(f"분석 실패: {str(e)}\nscrep.exe가 같은 폴더에 있는지 확인하세요.")
        finally:
            if os.path.exists(json_temp): os.remove(json_temp)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = StarAnalyzer()
    window.show()
    sys.exit(app.exec())