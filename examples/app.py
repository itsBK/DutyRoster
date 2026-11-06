from flask import Flask, render_template
from calendar import monthrange

app = Flask(__name__)


@app.route("/roster/<int:year>/<int:month>")
def roster(year, month):

    days_in_month = monthrange(year, month)[1]

    employees = [
        {
            "id": 1,
            "employee": "Alice",
            "day_1": "E",
            "day_2": "E",
            "day_3": "L",
            "day_4": "L",
            "day_5": "OFF",
            "day_6": "E",
            "day_7": "E",
        },
        {
            "id": 2,
            "employee": "Bob",
            "day_1": "L",
            "day_2": "L",
            "day_3": "OFF",
            "day_4": "E",
            "day_5": "E",
            "day_6": "N",
            "day_7": "N",
        },
        {
            "id": 3,
            "employee": "Charlie",
            "day_1": "N",
            "day_2": "N",
            "day_3": "OFF",
            "day_4": "L",
            "day_5": "L",
            "day_6": "E",
            "day_7": "E",
        }
    ]

    return render_template(
        "roster.html",
        year=year,
        month=month,
        employees=employees,
        days_in_month=days_in_month
    )


if __name__ == "__main__":
    app.run(debug=True)
