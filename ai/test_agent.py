from ai.agent import ask

vprasanja = [
    "Kje je bilo zadnjih šest mesecev največje onesnaženje s posameznimi polutanti, ki so v podatkovni bazi? Ne raziskuj sheme -- že poznaš tabele: measurements, stations, pollutants. Sestavi pregled onesnaženja za vsak posamezen polutant za vse postaje po imenu station_name, padajoče. Pripravi tudi povprečne vrednosti in top 3 postaje na polutant, za povprečne vrednosti in za viške."
]

for vpr in vprasanja:
    print(f"\n{'='*70}")
    print(f"VPRAŠANJE: {vpr}")
    print('='*70)
    try:
        odgovor = ask(vpr)
        print(f"ODGOVOR: {odgovor}")
    except Exception as e:
        print(f"NAPAKA: {e}")