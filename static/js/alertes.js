function verifierAlertes() {
    $.ajax({
        url: "/api/alertes_medicaments",
        type: "GET",
        success: function (data) {
            if (data.length > 0) {
                $("#alerte-sonore")[0].play();
                alert("Attention ! Certains médicaments approchent de leur date d'expiration !");
            }
        }
    });
}

$(document).ready(function () {
    setInterval(verifierAlertes, 60000); // Vérifie toutes les 60 secondes
});
