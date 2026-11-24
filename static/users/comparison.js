for (const figure of document.querySelectorAll('[data-comparison-photo]')) {
    const image = figure.querySelector('img');
    const controls = figure.querySelector('.comparison-rotation');
    let rotation = 0;

    for (const button of controls.querySelectorAll('[data-rotation]')) {
        button.addEventListener('click', () => {
            rotation = (rotation + Number(button.dataset.rotation) + 360) % 360;
            image.style.transform = `rotate(${rotation}deg)`;
        });
    }
    controls.hidden = false;
}
