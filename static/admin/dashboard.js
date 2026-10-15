(() => {
    function clock() {
        const now = new Date();
        const timeZone = document.body.dataset.timezone;

        document.getElementById("admin-date").textContent =
            new Intl.DateTimeFormat("en-GB", {
                timeZone,
                weekday: "long",
                day: "numeric",
                month: "long",
                year: "numeric"
            }).format(now);

        document.getElementById("admin-time").textContent =
            new Intl.DateTimeFormat("en-GB", {
                timeZone,
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit"
            }).format(now);
    }

    clock();
    setInterval(clock, 1000);

    const mode = document.getElementById("report-mode");

    if (!mode) {
        return;
    }

    function syncFields() {
        const fields = [
            ["date-field", "daily"],
            ["month-field", "monthly"]
        ];

        for (const [id, value] of fields) {
            const field = document.getElementById(id);

            field.hidden = mode.value !== value;

            field.querySelector("input").disabled =
                field.hidden;
        }
    }

    mode.addEventListener("change", syncFields);
    syncFields();

    document.getElementById("teacher-filter")
        .addEventListener("change", () => {
            document.getElementById("class-filter").value = "";

            document.getElementById("report-filters")
                .requestSubmit();
        });

    const graph = JSON.parse(
        document.getElementById(
            "attendance-graph-data"
        ).textContent
    );

    const colors = [
        "#28b78e",
        "#ec6d81",
        "#eab54c",
        "#8f7ad1",
        "#b6c0cc"
    ];

    const namespace = "http://www.w3.org/2000/svg";

    function element(tag, attributes, content) {
        const node = document.createElementNS(
            namespace,
            tag
        );

        for (const [key, value] of Object.entries(attributes)) {
            node.setAttribute(key, value);
        }

        if (content !== undefined) {
            node.textContent = content;
        }

        return node;
    }

    function draw(id, labels, datasets) {
        const host = document.getElementById(
            id + "-chart"
        );

        const legend = document.getElementById(
            id + "-legend"
        );

        const peak = Math.max(
            0,
            ...datasets.flatMap(dataset => dataset.values)
        );

        if (!peak) {
            const empty = document.createElement("p");

            empty.className = "empty";

            empty.textContent =
                "No attendance data for this selection.";

            host.append(empty);
            return;
        }

        const width = Math.max(
            620,
            labels.length * 48
        );

        const height = 270;

        const left = 42;
        const right = 15;
        const top = 20;
        const bottom = 40;

        const plotHeight = height - top - bottom;

        const groupWidth =
            (width - left - right) / labels.length;

        const step = Math.max(
            1,
            Math.ceil(peak / 4)
        );

        const maximum = step * 4;

        const svg = element("svg", {
            viewBox: `0 0 ${width} ${height}`,
            width,
            height,
            role: "img",
            "aria-label": id + " attendance chart"
        });

        for (let index = 0; index <= 4; index++) {
            const y =
                height - bottom -
                (index / 4) * plotHeight;

            svg.append(
                element("line", {
                    x1: left,
                    x2: width - right,
                    y1: y,
                    y2: y,
                    stroke: "#edf0f4"
                })
            );

            svg.append(
                element("text", {
                    x: left - 8,
                    y: y + 4,
                    "text-anchor": "end",
                    fill: "#8b96a7",
                    "font-size": 10
                }, index * step)
            );
        }

        labels.forEach((label, index) => {
            const x = left + index * groupWidth;

            const usable = groupWidth * 0.78;

            const barWidth =
                usable / datasets.length;

            svg.append(
                element("text", {
                    x: x + groupWidth / 2,
                    y: height - 15,
                    "text-anchor": "middle",
                    fill: "#788397",
                    "font-size": 10
                }, label)
            );

            datasets.forEach((dataset, seriesIndex) => {
                const value = dataset.values[index];

                const barHeight =
                    value / maximum * plotHeight;

                const bar = element("rect", {
                    x:
                        x + groupWidth * 0.11 +
                        seriesIndex * barWidth,

                    y: height - bottom - barHeight,

                    width: Math.max(1, barWidth - 1),
                    height: barHeight,

                    rx: 2,
                    fill: dataset.color
                });

                bar.append(
                    element(
                        "title",
                        {},
                        `${label} · ${dataset.name}: ${value}`
                    )
                );

                svg.append(bar);
            });
        });

        host.append(svg);

        datasets.forEach(dataset => {
            const label = document.createElement("span");
            const dot = document.createElement("i");

            dot.style.backgroundColor = dataset.color;

            label.append(
                dot,
                document.createTextNode(dataset.name)
            );

            legend.append(label);
        });
    }

    if (graph.mode === "daily") {
        const day = graph.days[0];

        draw(
            "student",
            graph.statuses,
            [
                {
                    name: "Student-session records",
                    color: colors[0],
                    values: graph.statuses.map(
                        status => graph.student[day][status]
                    )
                }
            ]
        );

        draw(
            "teacher",
            [day],
            [
                {
                    name: "Check-ins",
                    color: "#28b78e",
                    values: [graph.teacher[day].ins]
                },
                {
                    name: "Check-outs",
                    color: "#6286ee",
                    values: [graph.teacher[day].outs]
                }
            ]
        );

    } else {
        const labels = graph.days.map(
            day => day.slice(-2)
        );

        draw(
            "student",
            labels,
            graph.statuses.map((status, index) => ({
                name: status,
                color: colors[index],

                values: graph.days.map(
                    day => graph.student[day][status]
                )
            }))
        );

        draw(
            "teacher",
            labels,
            [
                {
                    name: "Check-ins",
                    color: "#28b78e",

                    values: graph.days.map(
                        day => graph.teacher[day].ins
                    )
                },
                {
                    name: "Check-outs",
                    color: "#6286ee",

                    values: graph.days.map(
                        day => graph.teacher[day].outs
                    )
                }
            ]
        );
    }
})();