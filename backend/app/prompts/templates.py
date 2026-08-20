
TEMPLATES: dict[str, dict[str, str]] = {
    "flow_ack": {
        "en": "Got it!",
        "hi": "ठीक है!",
        "mr": "ठीक आहे!",
        "hinglish": "Theek hai!",
    },
    "order_start_prompt": {
        "en": "Your cart's empty right now - here's our menu! What would you like to add?",
        "hi": "आपका कार्ट अभी खाली है - यह रहा हमारा मेनू! आप क्या जोड़ना चाहेंगे?",
        "mr": "तुमची कार्ट सध्या रिकामी आहे - हा आमचा मेनू! तुम्हाला काय जोडायचे आहे?",
        "hinglish": "Aapka cart abhi khaali hai - yeh raha hamara menu! Aap kya add karna chahenge?",
    },
    "order_added": {
        "en": "Added {qty} x {item} to your order. Current total: Rs.{total}.",
        "hi": "आपके ऑर्डर में {item} x {qty} जोड़ दिया गया है। वर्तमान कुल: Rs.{total}।",
        "mr": "तुमच्या ऑर्डरमध्ये {item} x {qty} जोडले आहे. सध्याची एकूण रक्कम: Rs.{total}.",
        "hinglish": "Aapke order mein {item} x {qty} add kar diya hai. Current total: Rs.{total}.",
    },
    "order_added_multi": {
        "en": "Added {items} to your order. Current total: Rs.{total}.",
        "hi": "आपके ऑर्डर में {items} जोड़ दिया गया है। वर्तमान कुल: Rs.{total}।",
        "mr": "तुमच्या ऑर्डरमध्ये {items} जोडले आहे. सध्याची एकूण रक्कम: Rs.{total}.",
        "hinglish": "Aapke order mein {items} add kar diya hai. Current total: Rs.{total}.",
    },
    "order_removed": {
        "en": "Removed {item} from your order. Current total: Rs.{total}.",
        "hi": "{item} आपके ऑर्डर से हटा दिया गया है। वर्तमान कुल: Rs.{total}।",
        "mr": "{item} तुमच्या ऑर्डरमधून काढले आहे. सध्याची एकूण रक्कम: Rs.{total}.",
        "hinglish": "{item} aapke order se remove kar diya hai. Current total: Rs.{total}.",
    },
    "order_updated": {
        "en": "Updated {item} to {qty}. Current total: Rs.{total}.",
        "hi": "{item} की मात्रा {qty} कर दी गई है। वर्तमान कुल: Rs.{total}।",
        "mr": "{item} चे प्रमाण {qty} केले आहे. सध्याची एकूण रक्कम: Rs.{total}.",
        "hinglish": "{item} ki quantity {qty} kar di hai. Current total: Rs.{total}.",
    },
    "order_cleared": {
        "en": "Your cart's all cleared out - starting fresh!",
        "hi": "आपका कार्ट पूरी तरह खाली कर दिया गया है - नई शुरुआत करते हैं!",
        "mr": "तुमची कार्ट पूर्णपणे रिकामी केली आहे - नव्याने सुरुवात करूया!",
        "hinglish": "Aapka cart poori tarah clear kar diya hai - fresh start karte hain!",
    },
    "order_already_empty": {
        "en": "Your cart's already empty - nothing to clear!",
        "hi": "आपका कार्ट पहले से ही खाली है - हटाने के लिए कुछ नहीं है!",
        "mr": "तुमची कार्ट आधीच रिकामी आहे - काढण्यासाठी काहीच नाही!",
        "hinglish": "Aapka cart pehle se hi khaali hai - clear karne ko kuch nahi hai!",
    },
    "order_item_not_on_menu": {
        "en": 'I couldn\'t find "{item}" on our menu - could you double-check the name?',
        "hi": 'मुझे हमारे मेनू में "{item}" नहीं मिला - क्या आप नाम दोबारा जांच सकते हैं?',
        "mr": 'आम्हाला आमच्या मेनूमध्ये "{item}" सापडले नाही - कृपया नाव पुन्हा तपासाल का?',
        "hinglish": 'Mujhe hamare menu mein "{item}" nahi mila - naam ek baar dobara check kar sakte hain?',
    },
    "order_item_not_in_cart": {
        "en": 'I couldn\'t find "{item}" in your order.',
        "hi": 'मुझे आपके ऑर्डर में "{item}" नहीं मिला।',
        "mr": 'तुमच्या ऑर्डरमध्ये "{item}" सापडले नाही.',
        "hinglish": 'Mujhe aapke order mein "{item}" nahi mila.',
    },
    "order_ambiguous_options": {
        "en": "We have a few options: {options} - which one would you like?",
        "hi": "हमारे पास कुछ विकल्प हैं: {options} - आप कौन सा चाहेंगे?",
        "mr": "आमच्याकडे काही पर्याय आहेत: {options} - तुम्हाला कोणता हवा आहे?",
        "hinglish": "Hamare paas kuch options hain: {options} - aapko kaunsa chahiye?",
    },
    "order_clarify_suggestions": {
        "en": 'I couldn\'t find "{item}" - did you mean one of these: {options}?',
        "hi": 'मुझे "{item}" नहीं मिला - क्या आपका मतलब इनमें से कोई था: {options}?',
        "mr": 'मला "{item}" सापडले नाही - तुम्हाला यापैकी काही म्हणायचे होते का: {options}?',
        "hinglish": 'Mujhe "{item}" nahi mila - kya aapka matlab in mein se koi tha: {options}?',
    },
    "order_split_clarify": {
        "en": 'We don\'t have "{original}" - did you mean {item1}, {item2}, or both?',
        "hi": 'हमारे पास "{original}" नहीं है - क्या आपका मतलब {item1}, {item2}, या दोनों था?',
        "mr": 'आमच्याकडे "{original}" नाही - तुम्हाला {item1}, {item2}, की दोन्ही म्हणायचे होते का?',
        "hinglish": 'Hamare paas "{original}" nahi hai - kya aapka matlab {item1}, {item2}, ya dono tha?',
    },
    "order_upsell_suggestion": {
        "en": "Want to add {item} with that?",
        "hi": "क्या आप इसके साथ {item} जोड़ना चाहेंगे?",
        "mr": "तुम्हाला यासोबत {item} जोडायचे आहे का?",
        "hinglish": "Kya aap iske saath {item} bhi add karna chahenge?",
    },
    "order_addon_ambiguous_nudge": {
        "en": "No worries - just let me know if you'd like the {item} added, or we can move on to checkout whenever you're ready.",
        "hi": "कोई बात नहीं - अगर आप {item} जुड़वाना चाहें तो बता दीजिएगा, या जब चाहें चेकआउट पर आगे बढ़ सकते हैं।",
        "mr": "काही हरकत नाही - {item} जोडायचे असल्यास सांगा, किंवा तयार असाल तेव्हा चेकआउटकडे जाऊया.",
        "hinglish": "Koi baat nahi - agar {item} add karwana ho toh bata dijiyega, ya jab ready ho checkout pe aage badh sakte hain.",
    },
    "order_ask_what_to_add": {
        "en": "What would you like to add?",
        "hi": "आप क्या जोड़ना चाहेंगे?",
        "mr": "तुम्हाला काय जोडायचे आहे?",
        "hinglish": "Aap kya add karna chahenge?",
    },
    "order_ask_what_to_remove": {
        "en": "Which item would you like to remove?",
        "hi": "आप कौन सी वस्तु हटाना चाहेंगे?",
        "mr": "तुम्हाला कोणती वस्तू काढायची आहे?",
        "hinglish": "Kaunsi item remove karni hai?",
    },
    "order_ask_what_to_modify": {
        "en": "Which item, and what quantity?",
        "hi": "कौन सी वस्तु, और कितनी मात्रा?",
        "mr": "कोणती वस्तू, आणि किती प्रमाण?",
        "hinglish": "Kaunsi item, aur kitni quantity?",
    },
    "checkout_ask_name": {
        "en": "Great, let's get your order ready! Could I get your name?",
        "hi": "बढ़िया, चलिए आपका ऑर्डर तैयार करते हैं! आपका नाम बता सकते हैं?",
        "mr": "छान, चला तुमची ऑर्डर तयार करूया! तुमचे नाव सांगू शकाल का?",
        "hinglish": "Great, chaliye aapka order ready karte hain! Aapka naam bata sakte hain?",
    },
    "checkout_ask_phone": {
        "en": "And a contact number for this order?",
        "hi": "और इस ऑर्डर के लिए एक संपर्क नंबर?",
        "mr": "आणि या ऑर्डरसाठी एक संपर्क क्रमांक?",
        "hinglish": "Aur is order ke liye ek contact number?",
    },
    "checkout_ask_email": {
        "en": "What's your email? I'll send your confirmation there.",
        "hi": "आपका ईमेल क्या है? मैं वहां आपकी पुष्टि भेज दूंगी।",
        "mr": "तुमचा ईमेल काय आहे? मी तिथे तुमची पुष्टी पाठवेन.",
        "hinglish": "Aapka email kya hai? Main wahan confirmation bhej doongi.",
    },
    "checkout_ask_birthday": {
        "en": "One more thing - is today someone's birthday? 🎂",
        "hi": "एक और बात - क्या आज किसी का जन्मदिन है? 🎂",
        "mr": "आणखी एक गोष्ट - आज कोणाचा वाढदिवस आहे का? 🎂",
        "hinglish": "Ek aur baat - aaj kisi ka birthday hai kya? 🎂",
    },
    "checkout_ask_fulfillment": {
        "en": "Would you like pickup or delivery?",
        "hi": "क्या आप पिकअप या डिलीवरी चाहेंगे?",
        "mr": "तुम्हाला पिकअप हवे आहे की डिलिव्हरी?",
        "hinglish": "Aapko pickup chahiye ya delivery?",
    },
    "checkout_ask_address": {
        "en": "Got it! Please select your delivery address using the map below.",
        "hi": "ठीक है! कृपया नीचे दिए गए मैप से अपना डिलीवरी पता चुनें।",
        "mr": "ठीक आहे! कृपया खालील नकाशावरून तुमचा डिलिव्हरी पत्ता निवडा.",
        "hinglish": "Got it! Neeche diye gaye map se apna delivery address select karein.",
    },
    "checkout_ask_reuse_address": {
        "en": "Deliver to your last address - {address}? Or search for a new one.",
        "hi": "क्या आपके पिछले पते पर डिलीवर करें - {address}? या नया पता खोजें।",
        "mr": "तुमच्या मागील पत्त्यावर डिलिव्हर करू का - {address}? किंवा नवीन पत्ता शोधा.",
        "hinglish": "Aapke last address par deliver karein - {address}? Ya naya address search karein.",
    },
    "checkout_address_must_select_suggestion": {
        "en": "Please pick your address from the suggestions dropdown as you type - if nothing matches yet, try refining your search.",
        "hi": "कृपया टाइप करते समय सुझाव सूची में से अपना पता चुनें - अगर अभी कुछ मेल नहीं खाता, तो अपनी खोज को और स्पष्ट करें।",
        "mr": "कृपया टाइप करताना सूचनांच्या यादीतून तुमचा पत्ता निवडा - अजून काही जुळत नसेल, तर तुमचा शोध अधिक स्पष्ट करा.",
        "hinglish": "Please type karte waqt suggestions dropdown se apna address select karein - abhi kuch match nahi ho raha toh apni search thodi aur specific karein.",
    },
    "checkout_ask_flat_number": {
        "en": "What's your house/flat number?",
        "hi": "आपका घर/फ्लैट नंबर क्या है?",
        "mr": "तुमचा घर/फ्लॅट नंबर काय आहे?",
        "hinglish": "Aapka house/flat number kya hai?",
    },
    "checkout_confirm_address": {
        "en": "Delivering to: {address}. Is this correct?",
        "hi": "डिलीवरी यहाँ होगी: {address}। क्या यह सही है?",
        "mr": "डिलिव्हरी येथे होईल: {address}. हे बरोबर आहे का?",
        "hinglish": "Delivery yahan hogi: {address}. Kya yeh sahi hai?",
    },
    "checkout_ask_pickup_location": {
        "en": "Which of our locations would you like to pick up from?",
        "hi": "आप हमारी किस लोकेशन से पिकअप करना चाहेंगे?",
        "mr": "तुम्हाला आमच्या कोणत्या ठिकाणाहून पिकअप करायचे आहे?",
        "hinglish": "Aap hamari kaunsi location se pickup karna chahenge?",
    },
    "checkout_address_out_of_range": {
        "en": "Sorry, we don't deliver that far. Please choose a closer address, or contact us at {phone}.",
        "hi": "क्षमा करें, हम इतनी दूर डिलीवरी नहीं करते। कृपया कोई नज़दीकी पता चुनें, या हमसे {phone} पर संपर्क करें।",
        "mr": "माफ करा, आम्ही इतक्या दूर डिलिव्हरी करत नाही. कृपया जवळचा पत्ता निवडा, किंवा आमच्याशी {phone} वर संपर्क साधा.",
        "hinglish": "Sorry, hum itni door deliver nahi karte. Please koi nazdeeki address choose karein, ya humse {phone} par contact karein.",
    },
    "checkout_delivery_confirmed_branch": {
        "en": "Great, that's within range - {location} will handle your delivery.",
        "hi": "बढ़िया, यह सीमा के भीतर है - {location} आपकी डिलीवरी संभालेगा।",
        "mr": "छान, हे मर्यादेत आहे - {location} तुमची डिलिव्हरी हाताळेल.",
        "hinglish": "Great, yeh range ke andar hai - {location} aapki delivery handle karega.",
    },
    "checkout_payment_prompt": {
        "en": "Here's your order summary. A payment is required to confirm it.",
        "hi": "यह रहा आपका ऑर्डर सारांश। इसे पक्का करने के लिए भुगतान आवश्यक है।",
        "mr": "हा तुमचा ऑर्डर सारांश आहे. तो निश्चित करण्यासाठी पेमेंट आवश्यक आहे.",
        "hinglish": "Yeh raha aapka order summary. Ise confirm karne ke liye payment zaroori hai.",
    },
    "order_mock_payment_confirmed": {
        "en": "Order confirmed! Your order will be ready for {fulfillment} shortly at our {location} branch. Order ID: #{order_id}",
        "hi": "ऑर्डर पक्का हो गया! आपका ऑर्डर हमारी {location} शाखा में {fulfillment} के लिए जल्द तैयार होगा। ऑर्डर आईडी: #{order_id}",
        "mr": "ऑर्डर निश्चित झाली! तुमची ऑर्डर आमच्या {location} शाखेत {fulfillment} साठी लवकरच तयार होईल. ऑर्डर आयडी: #{order_id}",
        "hinglish": "Order confirm ho gaya! Aapka order hamari {location} branch mein {fulfillment} ke liye jald ready hoga. Order ID: #{order_id}",
    },
    "order_summary_empty": {
        "en": "Your order is currently empty.",
        "hi": "आपका ऑर्डर अभी खाली है।",
        "mr": "तुमची ऑर्डर सध्या रिकामी आहे.",
        "hinglish": "Aapka order abhi khaali hai.",
    },
    "order_summary_line": {
        "en": "Your order so far: {lines}. Subtotal: Rs.{subtotal}, Tax: Rs.{tax}, Total: Rs.{total}.",
        "hi": "अब तक आपका ऑर्डर: {lines}। उप-योग: Rs.{subtotal}, कर: Rs.{tax}, कुल: Rs.{total}।",
        "mr": "आतापर्यंतची तुमची ऑर्डर: {lines}. उपबेरीज: Rs.{subtotal}, कर: Rs.{tax}, एकूण: Rs.{total}.",
        "hinglish": "Abhi tak aapka order: {lines}. Subtotal: Rs.{subtotal}, Tax: Rs.{tax}, Total: Rs.{total}.",
    },
    "reservation_ask_location": {
        "en": "Which of our locations would you like to book at?",
        "hi": "आप हमारी किस लोकेशन पर बुकिंग करना चाहेंगे?",
        "mr": "तुम्हाला आमच्या कोणत्या ठिकाणी बुकिंग करायची आहे?",
        "hinglish": "Aap hamari kaunsi location par booking karna chahenge?",
    },
    "reservation_ask_date": {
        "en": "What date would you like to book for?",
        "hi": "आप किस तारीख के लिए बुकिंग करना चाहेंगे?",
        "mr": "तुम्हाला कोणत्या तारखेसाठी बुकिंग करायचे आहे?",
        "hinglish": "Aap kis date ke liye booking karna chahenge?",
    },
    "reservation_ask_time": {
        "en": "What time would you like to book for?",
        "hi": "आप किस समय के लिए बुकिंग करना चाहेंगे?",
        "mr": "तुम्हाला कोणत्या वेळेसाठी बुकिंग करायचे आहे?",
        "hinglish": "Aap kis time ke liye booking karna chahenge?",
    },
    "reservation_ask_guests": {
        "en": "How many guests will be joining?",
        "hi": "कितने मेहमान शामिल होंगे?",
        "mr": "किती पाहुणे सामील होतील?",
        "hinglish": "Kitne guests aa rahe hain?",
    },
    "reservation_ask_name": {
        "en": "Great! Could I get your name for the booking?",
        "hi": "बढ़िया! बुकिंग के लिए आपका नाम बता सकते हैं?",
        "mr": "छान! बुकिंगसाठी तुमचे नाव सांगू शकाल का?",
        "hinglish": "Great! Booking ke liye aapka naam bata sakte hain?",
    },
    "reservation_ask_phone": {
        "en": "And a contact number so we can reach you if needed?",
        "hi": "और एक संपर्क नंबर, ताकि ज़रूरत पड़ने पर हम आपसे संपर्क कर सकें?",
        "mr": "आणि एक संपर्क क्रमांक, गरज पडल्यास आम्ही तुमच्याशी संपर्क करू शकतो का?",
        "hinglish": "Aur ek contact number, taaki zaroorat padne par aapse contact kar sakein?",
    },
    "reservation_invalid_phone": {
        "en": "That doesn't look like a valid phone number - could you share a 10-digit number?",
        "hi": "यह मान्य फ़ोन नंबर नहीं लगता - क्या आप 10 अंकों का नंबर बता सकते हैं?",
        "mr": "हा वैध फोन नंबर वाटत नाही - कृपया 10 अंकी क्रमांक सांगाल का?",
        "hinglish": "Yeh valid phone number nahi lag raha - 10 digit ka number bata sakte hain?",
    },
    "reservation_ask_email": {
        "en": "What's your email? I'll send your confirmation (and a reminder before your booking) there.",
        "hi": "आपका ईमेल क्या है? मैं वहां आपकी पुष्टि (और बुकिंग से पहले एक रिमाइंडर) भेज दूंगी।",
        "mr": "तुमचा ईमेल काय आहे? मी तिथे तुमची पुष्टी (आणि बुकिंगपूर्वी एक रिमाइंडर) पाठवेन.",
        "hinglish": "Aapka email kya hai? Main wahan confirmation (aur booking se pehle ek reminder) bhej doongi.",
    },
    "invalid_email": {
        "en": "That doesn't look like a valid email address - could you double-check it?",
        "hi": "यह मान्य ईमेल पता नहीं लगता - क्या आप दोबारा जांच सकते हैं?",
        "mr": "हा वैध ईमेल पत्ता वाटत नाही - कृपया पुन्हा तपासाल का?",
        "hinglish": "Yeh valid email nahi lag raha - ek baar dobara check kar sakte hain?",
    },
    "reservation_ask_birthday": {
        "en": "One more thing - is today someone's birthday? 🎂",
        "hi": "एक और बात - क्या आज किसी का जन्मदिन है? 🎂",
        "mr": "आणखी एक गोष्ट - आज कोणाचा वाढदिवस आहे का? 🎂",
        "hinglish": "Ek aur baat - aaj kisi ka birthday hai kya? 🎂",
    },
    "reservation_ask_special_requests": {
        "en": "Any special requests? (or type 'no' to skip)",
        "hi": "कोई खास अनुरोध? (छोड़ने के लिए 'नहीं' लिखें)",
        "mr": "काही खास विनंती आहे का? (वगळण्यासाठी 'नाही' लिहा)",
        "hinglish": "Koi special request hai? (skip karne ke liye 'no' likhein)",
    },
    "reservation_confirm_summary": {
        "en": "Just to confirm: table for {guests} on {date} at {time} under {name} at our {location} branch, contact {phone}. Shall I go ahead and book it?",
        "hi": "पुष्टि के लिए: {name} के नाम पर {guests} लोगों के लिए {date} को {time} पर हमारी {location} शाखा में टेबल, संपर्क {phone}। क्या मैं आगे बढ़कर बुक कर दूं?",
        "mr": "पुष्टीसाठी: {name} यांच्या नावावर {guests} जणांसाठी {date} रोजी {time} वाजता आमच्या {location} शाखेत टेबल, संपर्क {phone}. मी पुढे जाऊन बुक करू का?",
        "hinglish": "Confirm karne ke liye: {name} ke naam par {guests} logon ke liye {date} ko {time} par hamari {location} branch mein table, contact {phone}. Kya main aage badhkar book kar doon?",
    },
    "reservation_booked": {
        "en": "Booked! Table for {guests} on {date} at {time} under {name} at our {location} branch. We'll call {phone} if anything changes. See you soon!",
        "hi": "बुक हो गया! {name} के नाम पर {guests} लोगों के लिए {date} को {time} पर हमारी {location} शाखा में टेबल। कुछ बदलाव हुआ तो हम {phone} पर कॉल करेंगे। जल्द मिलते हैं!",
        "mr": "बुक झाले! {name} यांच्या नावावर {guests} जणांसाठी {date} रोजी {time} वाजता आमच्या {location} शाखेत टेबल. काही बदल झाल्यास आम्ही {phone} वर कॉल करू. लवकरच भेटू!",
        "hinglish": "Booked! {name} ke naam par {guests} logon ke liye {date} ko {time} par hamari {location} branch mein table. Kuch change hua toh hum {phone} par call karenge. Jald milte hain!",
    },
    "reservation_cancelled": {
        "en": "No problem, I've cancelled that booking request - just let me know if you'd like to start over!",
        "hi": "कोई बात नहीं, मैंने वह बुकिंग अनुरोध रद्द कर दिया है - अगर आप फिर से शुरू करना चाहें तो बताइए!",
        "mr": "काही हरकत नाही, मी ती बुकिंग विनंती रद्द केली आहे - पुन्हा सुरू करायचे असल्यास सांगा!",
        "hinglish": "Koi baat nahi, maine wo booking request cancel kar di hai - dobara start karna ho toh bata dena!",
    },
    "reservation_payment_prompt": {
        "en": "A ₹50 booking fee is required to confirm your table.",
        "hi": "आपकी टेबल पक्की करने के लिए ₹50 बुकिंग शुल्क देना होगा।",
        "mr": "तुमचे टेबल निश्चित करण्यासाठी ₹50 बुकिंग शुल्क आवश्यक आहे.",
        "hinglish": "Aapki table confirm karne ke liye ₹50 booking fee dena hoga.",
    },
    "reservation_cant_parse": {
        "en": "Sorry, I couldn't quite understand that date/time - could you try something like 'tomorrow at 7pm'?",
        "hi": "क्षमा करें, मुझे वह तारीख/समय समझ नहीं आया - क्या आप 'कल शाम 7 बजे' जैसा कुछ बता सकते हैं?",
        "mr": "माफ करा, मला ती तारीख/वेळ समजली नाही - कृपया 'उद्या संध्याकाळी ७ वाजता' असे काहीतरी सांगाल का?",
        "hinglish": "Sorry, mujhe wo date/time samajh nahi aaya - 'kal shaam 7 baje' jaisa kuch try kar sakte hain?",
    },
    "reservation_unavailable": {
        "en": "Sorry, that slot isn't available ({reason}).",
        "hi": "क्षमा करें, वह समय उपलब्ध नहीं है ({reason})।",
        "mr": "माफ करा, ती वेळ उपलब्ध नाही ({reason}).",
        "hinglish": "Sorry, wo slot available nahi hai ({reason}).",
    },
    "reservation_alternatives": {
        "en": " How about one of these times instead: {alts}?",
        "hi": " इसके बजाय इनमें से कोई समय कैसा रहेगा: {alts}?",
        "mr": " त्याऐवजी यापैकी एखादी वेळ कशी वाटते: {alts}?",
        "hinglish": " Iske bajaye in mein se koi time kaisa rahega: {alts}?",
    },
    "escalation_response": {
        "en": "I'm really sorry to hear that. I've made a note of this for our team. If you'd like to speak to someone directly, please call us at {phone}.",
        "hi": "यह सुनकर मुझे बहुत खेद है। मैंने इसे हमारी टीम के लिए नोट कर लिया है। अगर आप सीधे किसी से बात करना चाहें, तो कृपया हमें {phone} पर कॉल करें।",
        "mr": "हे ऐकून मला खूप वाईट वाटले. मी हे आमच्या टीमसाठी नोंदवले आहे. तुम्हाला थेट कोणाशी बोलायचे असल्यास, कृपया आम्हाला {phone} वर कॉल करा.",
        "hinglish": "Yeh sunkar mujhe bahut afsos hua. Maine iski note hamari team ke liye kar li hai. Agar aap directly kisi se baat karna chahein, toh please humein {phone} par call karein.",
    },
    "feedback_request": {
        "en": "How was everything? We'd love your feedback! 🙂",
        "hi": "सब कैसा रहा? हमें आपकी प्रतिक्रिया जानकर खुशी होगी! 🙂",
        "mr": "सर्व कसे झाले? आम्हाला तुमचा अभिप्राय आवडेल! 🙂",
        "hinglish": "Sab kaisa raha? Hume aapka feedback jaan kar accha lagega! 🙂",
    },
    "feedback_thank_you": {
        "en": "Thank you so much for your feedback! We really appreciate it. 🙏",
        "hi": "आपकी प्रतिक्रिया के लिए बहुत बहुत धन्यवाद! हम इसकी सराहना करते हैं। 🙏",
        "mr": "तुमच्या अभिप्रायाबद्दल खूप खूप धन्यवाद! आम्ही याची कदर करतो. 🙏",
        "hinglish": "Aapke feedback ke liye bahut bahut dhanyawad! Hum isko sach mein appreciate karte hain. 🙏",
    },
    "faq_location_intro": {
        "en": "We've got three cozy spots for you to choose from!",
        "hi": "हमारे पास आपके लिए तीन आरामदायक जगहें हैं!",
        "mr": "तुमच्यासाठी आमची तीन आरामदायक ठिकाणे आहेत!",
        "hinglish": "Hamare paas aapke liye teen cozy locations hain!",
    },
    "faq_about_intro": {
        "en": (
            "Rasa Café was born from a simple belief — that great coffee can bring people together. "
            "We're more than just a café. We're a cozy corner in your day, a space to slow down, "
            "share stories, and savor the little things.\n\n"
            "We host coffee brewing workshops, acoustic chai evenings, and more throughout the month.\n\n"
            "You'll find us at three locations:\n\n{locations}"
        ),
    },
}


def t(key: str, lang: str = "en", **kwargs) -> str:
    entry = TEMPLATES.get(key, {})
    template = entry.get(lang) or entry.get("en", "")
    return template.format(**kwargs)
