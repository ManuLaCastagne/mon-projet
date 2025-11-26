import tkinter as tk
from tkinter import simpledialog, messagebox

# Simuler une question
question = "Dans quel film sorti en 2012 voit-on Katniss Everdeen tirer à l'arc ?"
reponse = "Hunger Games"
score = 5  # score initial

def update_score(val):
    global score
    if val == "+1":
        score = min(score + 1, 10)
    elif val == "-1":
        score = max(score - 1, 0)
    elif val == "set":
        s = simpledialog.askinteger("Entrer un score", "Score entre 0 et 10 :", minvalue=0, maxvalue=10)
        if s is not None:
            score = s
    elif val == "supprimer":
        messagebox.showinfo("Suppression", "Question supprimée.")
        root.destroy()
        return

    label_score.config(text=f"Score : {score}")

# Interface
root = tk.Tk()
root.title("Quiz Culture G")

label_q = tk.Label(root, text=question, wraplength=400, font=("Helvetica", 14))
label_q.pack(pady=10)

btn_show = tk.Button(root, text="Afficher la réponse", command=lambda: messagebox.showinfo("Réponse", reponse))
btn_show.pack()

label_score = tk.Label(root, text=f"Score : {score}", font=("Helvetica", 12, "bold"))
label_score.pack(pady=10)

frame = tk.Frame(root)
frame.pack(pady=5)

tk.Button(frame, text="+1", width=5, command=lambda: update_score("+1")).grid(row=0, column=0, padx=5)
tk.Button(frame, text="-1", width=5, command=lambda: update_score("-1")).grid(row=0, column=1, padx=5)
tk.Button(frame, text="Set", width=5, command=lambda: update_score("set")).grid(row=0, column=2, padx=5)
tk.Button(frame, text="🗑 Supprimer", width=10, command=lambda: update_score("supprimer")).grid(row=0, column=3, padx=10)

root.mainloop()