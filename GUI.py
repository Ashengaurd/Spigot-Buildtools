from math import sqrt
from threading import Thread
from time import sleep
from tkinter import *
from tkinter.font import Font

from psutil import net_io_counters as net

from classes import Worker


class NetworkMeter(Label):
    FORMAT = "Received: {0}, Sent: {1}, Speed: {2}"

    def __init__(self, parent):
        Label.__init__(self, parent, text=NetworkMeter.FORMAT.format('0B', '0B', '0B'))

        first = net()
        self._f_recv = first.bytes_recv
        self._f_sent = first.bytes_sent
        self._l_recv = self._f_recv
        self._l_sent = self._f_sent

        Thread(target=self.update_text, daemon=True).start()

    def update_text(self):
        while True:
            result = net()
            recv = result.bytes_recv - self._f_recv
            sent = result.bytes_sent - self._f_sent
            speed = (result.bytes_recv + result.bytes_sent - self._l_recv - self._l_sent) * 2
            self._l_recv = result.bytes_recv
            self._l_sent = result.bytes_sent

            text = NetworkMeter.FORMAT.format(self.calculate(recv), self.calculate(sent), f'{self.calculate(speed)}ps')
            self.config(text=text)
            sleep(0.5)

    def calculate(self, value):
        bytes_list = ['B', 'KB', 'MB', 'GB', 'TB']
        byte = 'TB'
        for B in bytes_list:
            if value < 1024:
                byte = B
                break
            value /= 1024
        return f'{round(value, 2)}{byte}'


class LoggerUI(LabelFrame):
    def __init__(self, parent, queue, handler, name="Logger", **kwargs):
        LabelFrame.__init__(self, parent, text=name, **kwargs)

        textContainer = Frame(self, borderwidth=1, relief="sunken")
        self.text = Text(textContainer, width=40, height=10, wrap="none", borderwidth=0)
        textVsb = Scrollbar(textContainer, orient="vertical", command=self.text.yview)
        textHsb = Scrollbar(textContainer, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=textVsb.set, xscrollcommand=textHsb.set, font=Font(family='consolas', size=10))
        self.text.tag_config('INFO', foreground='green')
        self.text.tag_config('CONSOLE', foreground='white', background='black')
        self.text.tag_config('CONSOLE_ERROR', foreground='red', background='black')
        self.text.tag_config('DEBUG', foreground='gray')
        self.text.tag_config('WARNING', foreground='orange')
        self.text.tag_config('ERROR', foreground='red')
        self.text.tag_config('CRITICAL', foreground='red', underline=1)

        self.text.grid(row=0, column=0, sticky="nsew")
        textVsb.grid(row=0, column=1, sticky="ns")
        textHsb.grid(row=1, column=0, sticky="ew")
        textContainer.grid_rowconfigure(0, weight=1)
        textContainer.grid_columnconfigure(0, weight=1)
        textContainer.pack(side="top", fill="both", expand=True)

        self.handler = handler
        self.queue = queue

        Thread(target=self.poll_log_queue, daemon=True).start()

    def display(self, record):
        msg = self.handler.format(record)
        self.text.configure(state='normal')
        self.text.insert(END, msg + '\n', record.levelname)
        self.text.configure(state='disabled')
        self.text.yview(END)

    def poll_log_queue(self):
        while True:
            try:
                record = self.queue.get(False)
                self.display(record)
            except Exception:
                sleep(0.2)


class ChecklistBox(Frame):
    def __init__(self, parent, choices: list, selected=False, ipc=1.2, **kwargs):
        Frame.__init__(self, parent, **kwargs)

        s = round(sqrt(len(choices) * ipc))
        self.map = {}
        self.vars = []
        for i in range(len(choices)):
            bg = self.cget("background")
            choice = choices[i]
            self.map[str(choice)] = choice

            var = StringVar(value=choice)
            self.vars.append(var)

            cb = Checkbutton(self, var=var, text=choice, onvalue=choice, offvalue="", anchor="w", width=20, background=bg, relief="flat", highlightthickness=0)
            if selected:
                cb.select()
            else:
                cb.deselect()
            cb.grid(column=i // s, row=i % s)

    def getCheckedItems(self):
        values = []
        for var in self.vars:
            value = var.get()
            if value:
                values.append(self.map[value])
        return values


class APP(Tk):
    def __init__(self, queue):
        Tk.__init__(self)

        self.title("Spigot Build Tools - Made by AGMDevelopment")
        self.iconbitmap('./icon.ico')
        self.resizable(False, False)
        self.queue = queue

        versions = Frame(self)
        versions.grid(column=0, row=0, sticky="W")

        craftbukkit = Frame(versions)
        craftbukkit.grid(column=1, row=0, sticky="NW")

        label = Label(craftbukkit, text="For 1.14+ Only")
        label.grid(column=0, row=0, sticky="W")

        self.craft = ChecklistBox(craftbukkit, ["Craft Bukkit"], selected=True)
        self.craft.grid(column=0, row=1, sticky="W")

        from main import VERSIONS
        self.list = ChecklistBox(versions, VERSIONS)
        self.list.grid(column=0, row=0, sticky="W")

        frame = Frame(self)
        frame.grid(column=0, row=1)

        btn1 = Button(frame, text="Queue versions", command=self.queue_all)
        btn1.grid(column=0, row=0, padx=10, pady=10)

        btn2 = Button(frame, text="More Workers", command=lambda: Worker.add(self.log_frame, self.queue))
        btn2.grid(column=1, row=0, padx=10, pady=10)

        btn3 = Button(frame, text="Less Workers", command=lambda: Worker.close_last())
        btn3.grid(column=2, row=0, padx=10, pady=10)

        self.log_frame = LabelFrame(self, text='Workers log')
        self.log_frame.grid(column=0, row=2)

        ntw = NetworkMeter(self)
        ntw.grid(column=0, row=3, sticky='w')

    def queue_all(self):
        craftbukkit = len(self.craft.getCheckedItems()) > 0
        for version in self.list.getCheckedItems():
            version.craftbukkit = craftbukkit
            self.queue.put(version)

    def start(self):
        from main import MAX_THREAD
        for _ in range(MAX_THREAD):
            Worker.add(self.log_frame, self.queue)

        self.mainloop()
