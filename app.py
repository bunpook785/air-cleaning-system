from flask import Flask, render_template, request, redirect, url_for, session
from datetime import date, datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# ข้อมูลเครื่องแอร์ตัวอย่าง (แทนฐานข้อมูล)
air_conditioners = {
    f"AC{str(i).zfill(3)}": {
        "serial": f"AC{str(i).zfill(3)}",
        "customer_name": "",
        "customer_phone": "",
        "last_clean_date": None,
        "next_clean_date": None,
        "notes": ""
    } for i in range(1, 301)
}

# รหัสผ่านช่าง (ง่ายๆ)
TECHNICIAN_PASSWORD = "1234"

@app.route("/")
def home():
    return "ระบบนัดล้างแอร์ออนไลน์"

@app.route("/ac/<ac_id>")
def show_ac(ac_id):
    ac = air_conditioners.get(ac_id)
    if not ac:
        return "ไม่พบข้อมูลเครื่องแอร์นี้", 404

    today = date.today()
    countdown = ""
    if ac["next_clean_date"]:
        next_date = datetime.strptime(ac["next_clean_date"], "%Y-%m-%d").date()
        diff_days = (next_date - today).days
        if diff_days > 0:
            countdown = f"เหลืออีก {diff_days} วันจนถึงวันนัดล้างแอร์"
        elif diff_days == 0:
            countdown = "วันนี้คือวันนัดล้างแอร์"
        else:
            countdown = "เลยวันนัดล้างแอร์มาแล้ว"

    # หน้าแสดงข้อมูล + ปุ่มช่างเข้าสู่ระบบ
    return render_template("show_ac.html", ac=ac, countdown=countdown)

@app.route("/ac/<ac_id>/login", methods=["GET", "POST"])
def technician_login(ac_id):
    if request.method == "POST":
        password = request.form.get("password")
        if password == TECHNICIAN_PASSWORD:
            session["technician_logged_in"] = True
            session["ac_id"] = ac_id
            return redirect(url_for("edit_ac", ac_id=ac_id))
        else:
            return render_template("login.html", ac_id=ac_id, error="รหัสผ่านไม่ถูกต้อง")
    return render_template("login.html", ac_id=ac_id)

@app.route("/ac/<ac_id>/edit", methods=["GET", "POST"])
def edit_ac(ac_id):
    if not session.get("technician_logged_in") or session.get("ac_id") != ac_id:
        return redirect(url_for("show_ac", ac_id=ac_id))
    ac = air_conditioners.get(ac_id)
    if not ac:
        return "ไม่พบข้อมูลเครื่องแอร์นี้", 404

    if request.method == "POST":
        ac["customer_name"] = request.form.get("customer_name", "")
        ac["customer_phone"] = request.form.get("customer_phone", "")
        ac["last_clean_date"] = request.form.get("last_clean_date", None)
        ac["next_clean_date"] = request.form.get("next_clean_date", None)
        ac["notes"] = request.form.get("notes", "")
        return redirect(url_for("show_ac", ac_id=ac_id))

    return render_template("edit_ac.html", ac=ac)

@app.route("/logout")
def logout():
    session.clear()
    return "ออกจากระบบเรียบร้อย"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
