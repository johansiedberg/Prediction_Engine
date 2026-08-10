def generate_ai_match_analysis(user_pred, match, all_preds_list, home_count, draw_count, away_count, total_preds):
    if total_preds == 0:
        return {
            'group': "📊 Ingen i gänget har vågat tippa ännu – fältet ligger helt öppet för första kaxiga draget!",
            'user': "🎯 Du har inte tippat matchen än... Sluta fega!",
            'standout': "⚡ Inga galna chanstagningar har registrerats än."
        }
    
    home_name = match.get_home_team_info()['name']
    away_name = match.get_away_team_info()['name']
    
    home_pct = round((home_count / total_preds) * 100)
    draw_pct = round((draw_count / total_preds) * 100)
    away_pct = round((away_count / total_preds) * 100)

    # 1. Match Field Analysis (Edgy, banter-filled group analysis)
    if home_pct >= 60:
        group_roast = f"🔥 Hela gänget har drabbats av massaövertro på {home_name} ({home_pct}%)! Alla springer i samma fälla – om {away_name} skräller lär det snyftas rejält i snackgruppen."
    elif away_pct >= 60:
        group_roast = f"🔥 Blint förtroende för {away_name} ({away_pct}%)! Grabbarna räknar med borta-slakt, men om hemmalaget reser sig blir det ett episkt haveri i tabellen."
    elif draw_pct >= 35:
        group_roast = f"⚖️ Tråkspelar-varning i gänget! Hela {draw_pct}% fegar ut och tippar kryss. Noll riskvilja – alla hoppas smyga åt sig billiga poäng."
    else:
        group_roast = f"⚔️ Total inbördes krigsstämning ({home_pct}% 1:a, {draw_pct}% X, {away_pct}% 2:a)! Polarna vägrar enas – här ska det hånas och hållas tummar i realtid."

    # 2. Individual Player Prediction Analysis (EXACTLY ONE EMOJI, sharp banter)
    if not user_pred:
        user_roast = "🎯 Du har inte ens vågat spika ditt tips än... Sluta maska och kliv in i matchen!"
    else:
        u_hg = user_pred.home_goals
        u_ag = user_pred.away_goals
        
        if u_hg == 0 and u_ag == 0:
            user_roast = f"🎯 Ditt tips ({u_hg}-{u_ag})? Allvarligt, ett 0-0-tips är tråkigare än målarfärg som torkar. Våga bjuda på mål!"
        elif u_hg > u_ag:
            if home_pct >= 55:
                user_roast = f"🎯 Ditt tips ({u_hg}-{u_ag} på {home_name}) ryggar flocken fegt och tryggt. Inga risker, bara hopp om att inte hamna sist."
            else:
                user_roast = f"🎯 Ditt tips ({u_hg}-{u_ag} på {home_name}) kör rakt mot strömmen! Kaxigt drag – eller ren galenskap som gänget kommer hånskratta åt."
        elif u_ag > u_hg:
            if away_pct >= 55:
                user_roast = f"🎯 Ditt tips ({u_hg}-{u_ag} på {away_name}) hänger på borta-tåget. Noll originalitet, men skönt om alla nollar tillsammans."
            else:
                user_roast = f"🎯 Ditt tips ({u_hg}-{u_ag} på {away_name}) utmanar polarna hårt. Slår detta in får resten käka upp sina garv."
        else:
            user_roast = f"🎯 Ditt tips ({u_hg}-{u_ag} oavgjort) är en beräknad helgardering. Ett lurigt smygardrag för att snuva gänget på poäng."

    # 3. Outlier / Standout Finding (Hilarious highlights, rivalry & wild tips)
    standout_roast = ""
    
    # Check for wild high-scoring predictions (total goals >= 5)
    wild_preds = [p for p in all_preds_list if (p['home_goals'] + p['away_goals']) >= 5]
    
    # Find unique exact scores
    score_counts = {}
    for p in all_preds_list:
        sc = f"{p['home_goals']}-{p['away_goals']}"
        score_counts[sc] = score_counts.get(sc, 0) + 1
    
    unique_players = [p['username'] for p in all_preds_list if score_counts[f"{p['home_goals']}-{p['away_goals']}"] == 1]

    if wild_preds:
        w = wild_preds[0]
        standout_roast = f"💣 Omgångens galning: {w['username']} tippar ett vilt {w['home_goals']}-{w['away_goals']}! Har personen överdoserat energidryck? Ett resultat som sätter hela internrivaliteten i gungning."
    elif unique_players:
        if len(unique_players) == 1:
            standout_roast = f"🔥 Ensam mot världen: {unique_players[0]} står helt solokvist om sitt exakta resultat. Genistämpel eller årets garv i tabellen!"
        else:
            standout_roast = f"⚡ Egna vägar: {', '.join(unique_players[:2])} vägrar följa strömmen och kör sina helt egna wildcards för att sänka sina rivaler."
    else:
        standout_roast = f"📊 Noll mod i fältet: Alla tippar förvånansvärt likt – det blir marginalerna som avgör vem som får hånskratta i helgen."

    return {
        'group': group_roast,
        'user': user_roast,
        'standout': standout_roast
    }
