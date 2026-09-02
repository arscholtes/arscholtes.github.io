const cards = [...document.querySelectorAll(".role-card")];

function setCardState(card, isOpen) {
  const button = card.querySelector(".role-toggle");
  const details = card.querySelector(".role-details");
  const symbol = card.querySelector(".toggle-symbol");

  card.classList.toggle("is-open", isOpen);
  button.setAttribute("aria-expanded", String(isOpen));
  symbol.textContent = isOpen ? "−" : "+";
  details.hidden = !isOpen;
}

cards.forEach((card) => {
  card.querySelector(".role-toggle").addEventListener("click", () => {
    const willOpen = !card.classList.contains("is-open");

    cards.forEach((otherCard) => {
      setCardState(otherCard, otherCard === card ? willOpen : false);
    });
  });
});