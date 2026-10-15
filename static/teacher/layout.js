const zone = document.body.dataset.timezone;

function tick() {
    const now = new Date();

    document.getElementById("live-date").textContent =
        new Intl.DateTimeFormat("en-GB", {
            timeZone: zone,
            weekday: "long",
            day: "numeric",
            month: "long",
            year: "numeric"
        }).format(now);

    document.getElementById("live-time").textContent =
        new Intl.DateTimeFormat("en-GB", {
            timeZone: zone,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit"
        }).format(now);
}

tick();
setInterval(tick, 1000);

document.getElementById("page-search").addEventListener(
    "input",
    function (event) {
        const query = event.target.value.trim().toLowerCase();

        document.querySelectorAll("[data-search]").forEach(
            function (item) {
                item.hidden = !item.dataset.search
                    .toLowerCase()
                    .includes(query);
            }
        );
    }
);