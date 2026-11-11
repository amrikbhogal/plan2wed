"""Editable ceremony summaries, paraphrased from the linked sources."""

SOCIETY = "https://www.sikhmissionarysociety.org/sms/smssikhism/ceremonies/marriage/"
GUIDE = "https://www.punjabiweddingorganizer.com/blog/order-of-a-sikh-wedding"

EVENT_DESCRIPTIONS = {
    "Roka / Thaka": "A family gathering to confirm the couple’s intention to marry, often marked by blessings, sweets and gifts.",
    "Chunni Chadana": "The groom’s family welcomes the bride with a chunni (scarf), often accompanied by gifts and blessings.",
    "Kurmai / Sagai (engagement)": "An engagement gathering where the families acknowledge the forthcoming marriage, often with prayers, gifts and an exchange of rings.",
    "Akhand Path": "An uninterrupted reading of the Guru Granth Sahib, usually lasting about 48 hours, held to seek blessings.",
    "Sangeet": "A musical celebration bringing relatives and friends together for wedding songs, dancing and performances.",
    "Mehndi": "A pre-wedding gathering where henna designs are applied to the bride’s hands and feet, often with music and family celebrations.",
    "Maiyan / Vatna": "A Punjabi pre-wedding custom in which relatives apply a turmeric-based paste to the bride or groom at their respective homes.",
    "Khare Charhna": "A traditional pre-wedding bath following the Vatna ceremony; the bride is seated on a small stool for bathing.",
    "Jaggo": "A lively night-time Punjabi celebration featuring singing, dancing and a decorated pot with lights, traditionally carried through the neighbourhood.",
    "Choora ceremony": "The bride receives her wedding bangles, traditionally red and white, from her maternal family; kaleere may also be attached.",
    "Baraat": "The groom’s wedding party travels to the ceremony venue, where the bride’s family welcomes them before the wedding.",
    "Milni": "A welcome gathering where corresponding relatives from each family meet and greet one another before the wedding ceremony.",
    "Anand Karaj": "The Sikh marriage ceremony, celebrated in the presence of the Guru Granth Sahib. The couple walks around the scripture during the four Laavan hymns, reflecting a shared spiritual journey and commitment to married life.",
    "Doli / Vidaai": "The farewell after the wedding, when the bride leaves her family home or wedding venue with her spouse.",
    "Reception": "A celebration after the wedding where family and friends gather for a meal, speeches, music and dancing.",
}

SOCIETY_EVENTS = {"Roka / Thaka", "Chunni Chadana", "Kurmai / Sagai (engagement)", "Maiyan / Vatna", "Khare Charhna", "Milni", "Anand Karaj", "Baraat"}


def suggested_description(name):
    return next((text for key, text in EVENT_DESCRIPTIONS.items() if key.casefold() == name.strip().casefold()), "")


def description_source(name, description):
    for key, text in EVENT_DESCRIPTIONS.items():
        if description == text and key.casefold() == name.strip().casefold():
            return {"url": SOCIETY if key in SOCIETY_EVENTS else GUIDE,
                    "label": "Sikh Missionary Society" if key in SOCIETY_EVENTS else "Punjabi Wedding Organizer"}
    return None
