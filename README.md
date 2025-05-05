
# BuzzPi

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)
![Django](https://img.shields.io/badge/built_with-Django-092E20?logo=django&logoColor=white)

**BuzzPi** is a self-hosted real-time buzzer system designed for youth camps, game shows and group activities.

## Features

- Real-time buzzer via websockets
- Admin Dashboard
- Team support
- Mobile-friendly UI
- Fully offline

## Run Locally

Clone the repository:
```bash
git clone https://github.com/Kokoio01/BuzzPi
cd BuzzPi
```

Create a virtual environment:
```bash
python -m venv venv
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Run database migrations:
```bash
python manage.py migrate
```

Collect Staticfiles
```bash
python manage.py collectstatic
```

Start the development server:
```bash
python manage.py runserver
```
