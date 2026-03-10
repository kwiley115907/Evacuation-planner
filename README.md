# Evacuation Plan Generator

A simple web application for creating **emergency evacuation maps** from building floor plans.

This tool allows users to upload a floor plan image and place safety markers such as exits, assembly points, elevators, fire extinguishers, and "You Are Here" locations. The application then generates a formatted evacuation map with a legend and emergency instructions.

Built using **Python**, **Streamlit**, and **Pillow**.

---

# Features

- Upload building floor plan images
- Place evacuation markers:
  - You Are Here (yellow stick figure)
  - EXIT signs
  - Assembly Points (AP)
  - Elevators (L1/L2/L3 with slash)
  - Fire Extinguishers
- Draw evacuation routes
- Emergency notes in **English and Spanish**
- Automatic legend generation
- Export final evacuation map

---

# Marker Symbols

| Symbol | Meaning |
|------|------|
| Yellow Stick Figure | You Are Here |
| EXIT Sign | Emergency Exit |
| L1/L2/L3 with Slash | Do Not Use Elevators |
| Purple Circle "AP" | Assembly Point |
| Fire Extinguisher Icon | Fire Extinguisher Location |

---

# Project Structure

```
evac-plan-app
│
├── app.py
├── README.md
├── requirements.txt
│
└── evacplan
    └── render_pil.py
```

### Files

**app.py**  
Main Streamlit application interface.

**render_pil.py**  
Handles drawing markers, routes, legends, and emergency notes using Pillow.

**requirements.txt**  
Python dependencies required to run the app.

---

# Installation

Install Python packages:

```
pip install -r requirements.txt
```

or manually:

```
pip install streamlit pillow
```

---

# Running the Application

Start the Streamlit server:

```
python -m streamlit run app.py
```

The application will open at:

```
http://localhost:8501
```

Open the URL in your browser.

---

# Usage

1. Upload a floor plan image.
2. Place safety markers by entering X/Y coordinates or tapping the map.
3. Assign rooms to exits.
4. Generate evacuation routes.
5. Export the completed evacuation map.

---

# Emergency Instructions (Displayed on Maps)

**English**

- In the event of an emergency call 911
- Calmly evacuate to emergency exits immediately
- Follow evacuation procedures
- Do not use elevators
- Proceed to your assembly point
- If obstacles arise choose the nearest/safest exit

**Spanish**

- En caso de emergencia llame al 911
- Evacúe con calma hacia las salidas de emergencia inmediatamente
- Siga los procedimientos de evacuación
- No use los elevadores
- Diríjase a su punto de reunión
- Si hay obstáculos elija la salida más cercana o más segura

---

# Technologies Used

- Python
- Streamlit
- Pillow (PIL)

---

# Future Improvements

- Click-to-place markers directly on the map
- Automatic route calculation
- PDF export
- Multi-floor building support
- User accounts for organizations
- QR code access to evacuation plans

---

# License

This project is provided for educational and safety planning purposes.

Use responsibly when creating emergency evacuation plans.
