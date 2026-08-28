# **Comprehensive Tactical Analysis of VALORANT Agent Mechanics and Quantitative Ability Specifications**

## **Fundamental Framework of VALORANT Ability Systems**

VALORANT combines precise gunplay with tactical agent utility1. Agents represent individual operatives within the VALORANT Protocol, structured into four specialized combat roles: Controllers, Sentinels, Initiators, and Duelists2. Regardless of role classification, every agent enters a round with a baseline health pool of 100 Health Points (HP), which can be supplemented with light armor (25 HP) or heavy armor (50 HP) to reach a maximum effective HP of 1502. Ability loadouts consist of four distinct slots: Basic abilities purchased during the pre-round Buy Phase using earned credits, a Signature ability provided automatically each round or recharged via specific conditions, and an Ultimate ability powered by accumulating points through kills, deaths, spike plants, spike defusals, and map-spawned Ultimate Orbs2.  
The competitive meta is governed by exact spatial and temporal constraints—cooldowns, windup delays, active durations, deployable health pools, debuff scaling, and credit costs5. Understanding these metrics is vital for economic management, site execution timing, and cross-class ability combinations5.

| Role Class | Strategic Core Function | Signature Recharge Mechanism | Roster Allocation |
| :---- | :---- | :---- | :---- |
| **Controller** | Vision occlusion, territory management, choke point control2 | Timed cooldowns (35s–40s) or fixed round charges4 | 7 Agents2 |
| **Sentinel** | Area interdiction, flank protection, defensive anchoring2 | Cooldown upon recall or destruction4 | 7 Agents2 |
| **Initiator** | Reconnaissance, angle clearing, target displacement2 | Timed cooldowns (60s) or retrievable utility4 | 7 Agents2 |
| **Duelist** | Entry fragging, spatial creation, isolated engagements2 | Combat performance (2 kills per round)2 | 8 Agents2 |

## **Controller Class: Quantitative Spatial Manipulation and Sightline Control**

Controllers manipulate lines of sight and dictate map flow through spherical smokes, toxic screens, molotovs, and area-denial crowd control2. The effectiveness of a Controller relies on smoke duration, deployable range, and overall uptime relative to the 45-second Spike detonation timer7.

| Agent | Smoke Ability | Active Duration | Windup / Cast Time | Cooldown / Recharge | Cost |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **Brimstone** | Sky Smoke | 19.25 seconds16 | Instant map cast16 | Purchased per round16 | 100 Credits16 |
| **Omen** | Dark Cover | 15.00 seconds9 | \~1.0s travel phase9 | 40 seconds cooldown9 | 150 Credits (1 Free)9 |
| **Astra** | Nebula | 14.25 seconds8 | Instant Star trigger8 | 35 seconds cooldown8 | 150 Credits per Star8 |
| **Clove** | Ruse (Alive) | 14.25 seconds17 | 1.0s deployment17 | 40 seconds cooldown17 | 150 Credits (1 Free)17 |
| **Clove** | Ruse (Dead) | 6.00 seconds17 | 1.0s deployment17 | 40 seconds cooldown17 | 150 Credits (1 Free)17 |

### **Brimstone**

Brimstone serves as a tactical commander capable of executing rapid multi-smoke setups via his wrist-mounted map16.

* **Stim Beacon (C)**: Cost: 200 Credits | Max Charges: 1 | Duration: 12.0s16. Deploys a beacon on the ground creating a 12-second field that grants allies a Combat Stim and a Speed Boost16. Affected players receive a \+10% bonus to Movement Speed, Fire Rate, Equip Speed, Reload Speed, and Recoil Recovery Speed16.  
* **Incendiary (Q)**: Cost: 250 Credits | Max Charges: 1 | Duration: 7.0s | Damage: 60 HP/s16. Launches a molotov grenade that detonates upon coming to rest on the floor, producing a continuous high-damage fire zone16.  
* **Sky Smoke (E \- Signature)**: Cost: 100 Credits | Max Charges: 3 | Duration: 19.25s16. Opens a tactical map display allowing Brimstone to drop up to three long-lasting, vision-blocking smoke spheres simultaneously within range16.  
* **Orbital Strike (X \- Ultimate)**: Cost: 8 Ultimate Points | Windup: 2.0s | Active Duration: 3.0s | Damage: 20 HP per tick (6.67 ticks/sec, \~200 DPS maximum)16. Launches an orbital laser beam at a designated location, dealing high damage over time while completely blocking vision and minimap tracking through the beam16.

### **Astra**

Astra operates from Astral Form to position Stars globally across the map, transforming them into crowd-control utility or vision-blocking smokes8.

* **Astral Form (Passive System)**: Free | Charges: Unlimited toggle8. Astra enters an elevated cosmic perspective to place Stars across the map8. While in Astral Form, she retains ambient audio awareness around her physical body8.  
* **Stars (Signature Pool)**: Cost: 150 Credits | Max Pool: 5 Stars | Recall Cooldown: 25s8. Stars placed on the map act as catalysts for her abilities; unused Stars carry over to subsequent rounds8. Dissipating a Star recalls it after 25 seconds while creating a 1.0-second fake smoke8.  
* **Gravity Well (C)**: Uses 1 Star | Windup: 1.25s | Pull Duration: 2.0s | Cooldown: 60s | Debuff: 2.5s Vulnerable8. Pulls nearby players toward the center before exploding, applying a Vulnerable debuff that causes affected targets to take double damage8.  
* **Nova Pulse (Q)**: Uses 1 Star | Windup: 1.0s | Cooldown: 60s | Debuff: 2.5s Concuss8. Charges briefly before detonating a seismic strike that concusses all targets within its area8.  
* **Nebula / Dissipate (E)**: Uses 1 Star | Duration: 14.25s (Nebula) / 1.0s (Dissipate) | Cooldown: 35s8. Transforms a target Star into a vision-blocking smoke cloud8. An audio and visual cue plays 1.5 seconds prior to expiration8.  
* **Cosmic Divide (X \- Ultimate)**: Cost: 7 Ultimate Points | Duration: 21.0s8. Places a wall spanning the entire map that blocks all bullets and dampens audio transmission8.

### **Omen**

Omen relies on renewable smoke placement and phase teleportation to disrupt enemy positions9.

* **Shrouded Step (C)**: Cost: 100 Credits | Max Charges: 2 | Channel Time: \~1.0s9. Teleports Omen to a targeted location within line of sight after a short channel9.  
* **Paranoia (Q)**: Cost: 250 Credits | Max Charges: 1 | Projectile Travel: Wall-piercing | Debuff Duration: 2.0s Nearsight and Deafen9. Casts a shadow projectile forward that passes directly through walls, nearsighting and deafening caught targets9.  
* **Dark Cover (E \- Signature)**: Cost: 150 Credits (First charge free) | Max Charges: 2 | Duration: 15.0s | Cooldown: 40s9. Launches a shadow orb into a phased target layer, spawning a hollow vision-blocking sphere9.  
* **From the Shadows (X \- Ultimate)**: Cost: 7 Ultimate Points | Channel Time: 4.0s9. Opens a global tactical map to teleport anywhere9. During the 4.0-second channel, Omen manifests as a destructible Shade; destroying the Shade cancels the teleport9.

### **Clove**

Clove focuses on post-death map control and aggressive self-sustain17.

* **Pick-me-up (C)**: Cost: 200 Credits | Max Charges: 1 | Windup: 0.7s | Buff Duration: 10.0s (Health) / 3.0s (Movement Speed) | Overheal: Up to \+50 HP17. Absorbs the essence of a damaged or killed enemy to grant temporary overheal HP and a \+15% movement speed boost17.  
* **Meddle (Q)**: Cost: 250 Credits | Max Charges: 1 | Windup: 0.75s after ground contact | Radius: 4.0m | Duration: 5.0s | Debuff: 90 HP Decay17. Throws an essence fragment that erupts upon hitting the floor, temporarily decaying targets by up to 90 HP17.  
* **Ruse (E \- Signature)**: Cost: 150 Credits (First charge free) | Max Charges: 2 | Duration: 14.0s (Alive) / 6.0s (Dead) | Cooldown: 40s17. Sets vision-blocking clouds on a tactical map UI17. Clove can cast this ability after dying, provided the target location is near their death location17.  
* **Not Dead Yet (X \- Ultimate)**: Cost: 8 Ultimate Points | Revive Channel: 1.5s | Intangibility Duration: Up to 2.0s | Elimination Window: 10.0s17. Resurrects Clove upon death; Clove must secure an enemy kill or damaging assist within 10 seconds to remain alive17.

### **Viper**

Viper uses a shared resource pool (Fuel) to manage her toxin utility dynamically19.

* **Fuel & Toxin Passive System**: Max Fuel Uptime: \~12.0s per single smoke | Dual Drain Penalty: \+50% fuel consumption when Toxic Screen and Poison Cloud are active simultaneously19. Fuel regenerates over 30 seconds when depleted19. Enemies contacting Viper's smoke suffer Toxin decay—an instant 30 HP drop followed by 10 HP/s decay down to 1 HP19. Health regenerates 1.5 seconds after exiting the gas at 25 HP/s19.  
* **Snake Bite (C)**: Cost: 300 Credits | Max Charges: 1 | Active Duration: 5.5s | Radius: 4.5m | Debuff: Vulnerable \+ Damage Over Time21. Fires a chemical canister that shatters on impact, creating a puddle that damages and applies Vulnerable21.  
* **Poison Cloud (Q)**: Cost: 200 Credits | Max Charges: 1 | Emitter Retrieval Range: 4.0m | Cooldown on Deactivation: 8.0s21. Throws a gas emitter that can be toggled on and off using Fuel21.  
* **Toxic Screen (E \- Signature)**: Cost: 300 Credits | Max Charges: 1 | Cooldown on Deactivation: 8.0s21. Launches a line of gas emitters creating a wall of toxic gas when activated21.  
* **Viper's Pit (X \- Ultimate)**: Cost: 8 Ultimate Points21. Emits a massive chemical cloud that expands through doorways and terrain, nearsighting enemies and applying heavy Toxin decay21.

## **Sentinel Class: Defensive Anchoring and Area Interdiction**

Sentinels secure objective sites, lock down choke points, and cover flanks using deployable traps, barriers, and autonomous utility2.

| Agent | Core Defensive Utility | Deployable Health | Windup / Arm Time | Recall Cooldown | Destruction Cooldown |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **Killjoy** | Alarmbot | 20 HP10 | Instant ground placement10 | 20 seconds10 | Permanent for round10 |
| **Killjoy** | Turret | 100 HP10 | Instant placement10 | 20 seconds10 | 60 seconds10 |
| **Killjoy** | Lockdown (Ultimate) | 200 HP10 | 13.0s windup10 | Cannot be recalled10 | Permanent for round10 |
| **Chamber** | Trademark | 20 HP11 | 2.0s arm time11 | 30 seconds11 | Permanent for round11 |
| **Chamber** | Rendezvous (Anchor) | 50 HP11 | Instant placement11 | 30 seconds11 | Permanent for round11 |
| **Sage** | Barrier Orb (Segment) | 400 HP \-\> 800 HP24 | 3.3s fortify time24 | Cannot be recalled24 | Shatters at 40s24 |

### **Killjoy**

Killjoy deploys autonomous devices to hold choke points and delay enemy attacks10.

* **Nanoswarm (C)**: Cost: 200 Credits | Max Charges: 2 | Deployable HP: 20 HP | Active Duration: 4.0s | Damage: 45 HP/s10. Throws a hidden grenade that can be remotely activated to release a swarm of damaging nanobots10.  
* **Alarmbot (Q)**: Cost: 200 Credits | Max Charges: 1 | Deployable HP: 20 HP | Recall Cooldown: 20s | Debuff: 4.0s Vulnerable10. Deploys a covert bot that hunts down enemies entering its detection range, exploding to apply Vulnerable10.  
* **Turret (E \- Signature)**: Cost: Free | Max Charges: 1 | Deployable HP: 100 HP | Recall Cooldown: 20s | Destruction Cooldown: 60s | Damage: 8 HP/shot (0–20m), 6 HP/shot (20–35m), 4 HP/shot (35m+)10. Fires 3-shot bursts in a 180-degree cone at spotted targets10.  
* **Lockdown (X \- Ultimate)**: Cost: 9 Ultimate Points | Deployable HP: 200 HP | Windup Delay: 13.0s | Debuff: 8.0s Detain10. Placed device counts down for 13 seconds before detaining all enemies caught within its large radius, disabling their weapons and abilities10.

### **Chamber**

Chamber uses custom firearms and short-range teleportation to take aggressive sightlines11.

* **Trademark (C)**: Cost: 200 Credits | Max Charges: 1 | Deployable HP: 20 HP | Arm Time: 2.0s | Recall Cooldown: 30s | Debuff: 4.0s 50% Slow11. Places a trap that scans for enemies, creating a lingering slow field when triggered11.  
* **Headhunter (Q)**: Cost: 100 Credits per bullet | Max Capacity: 8 bullets | Damage: 159 (Head), 55 (Body), 46 (Legs)11. Equips a heavy custom pistol capable of Aiming Down Sights (ADS)11.  
* **Rendezvous (E \- Signature)**: Cost: Free | Max Charges: 1 Anchor | Anchor HP: 50 HP | Teleport Radius: 18.0m | Cooldown: 30s (upon use or recall) | Post-Teleport Weapon Equip Delay: 0.7s11. Places a teleport anchor that Chamber can activate while within its 18m radius11.  
* **Tour De Force (X \- Ultimate)**: Cost: 8 Ultimate Points | Capacity: 5 bullets | Windup: 2.3s | Fire Rate: 0.9 rounds/s | Damage: 255 (Head), 150 (Body), 127 (Legs)11. Summons a heavy custom sniper rifle that kills enemies with a direct hit to the upper body, spawning a 4.0-second 50% slow field beneath killed targets11.

### **Sage**

Sage manages map tempo using solid barriers, slowing fields, and target restoration24.

* **Barrier Orb (C)**: Cost: 400 Credits | Max Charges: 1 | Cast Range: 10.0m | Max Duration: 40.0s | Segment Health: 400 HP initially, fortifying to 800 HP after 3.3s24. Places a solid four-segment wall24.  
* **Slow Orb (Q)**: Cost: 200 Credits | Max Charges: 2 | Active Duration: 7.0s | Slow Effect: 50% movement and air-speed reduction24. Launches an orb that shatters on ground contact, creating a slowing zone24.  
* **Healing Orb (E \- Signature)**: Cost: Free | Cooldown: 45s | Ally Healing: 100 HP over 5.0s | Self Healing: 30 HP over 5.0s24. Restores health over time to a targeted ally or herself24.  
* **Resurrection (X \- Ultimate)**: Cost: 7 Ultimate Points | Target Requirement: Close-range allied corpse24. Revives a targeted dead ally back to full health after a brief channel24.

### **Cypher**

Cypher builds a web of surveillance utility to track enemy movements26.

* **Trapwire (C)**: Cost: 200 Credits | Max Charges: 2 | Health: 20 HP | Maximum Length: 15.0m | Windup: 0.5s reveal fade-in | Effect: Tethers, reveals, and concusses caught targets if not destroyed26.  
* **Cyber Cage (Q)**: Cost: 100 Credits | Max Charges: 2 | Duration: 7.0s4. Throws a hidden trap that creates a hollow vision-blocking cylinder when activated remotely4.  
* **Spycam (E \- Signature)**: Cost: Free | Max Charges: 1 | Destruction Cooldown: 45s | Marking Dart Cooldown: 6.0s26. Places a camera that shoots hitscan darts, periodically revealing enemy locations26.  
* **Neural Theft (X \- Ultimate)**: Cost: 6 Ultimate Points | Maximum Range: 18.0m26. Targets a dead enemy corpse to reveal the location of all living enemies twice, with a 4.0-second delay between scans26.

## **Initiator Class: Intelligence Gathering and Crowd Control Vectors**

Initiators collect real-time positional intel and apply crowd control to clear corners and support site pushes2.

| Agent | Recon / CC Ability | Target HP / Armor | Active Duration | Target Impact / Debuff Output |
| :---- | :---- | :---- | :---- | :---- |
| **Sova** | Recon Bolt | 20 HP13 | 3.2s (2 Pulses)13 | 0.75s real-time reveal ping13 |
| **Sova** | Owl Drone | 100 HP13 | 7.0 seconds13 | 2 hitscan marking darts13 |
| **Fade** | Haunt | 1 HP12 | 1.5 seconds12 | 12.0s Terror Trail \+ reveal12 |
| **Fade** | Prowler | 60 HP12 | 2.5 seconds12 | 2.75s Nearsight debuff12 |
| **Skye** | Trailblazer | 80 HP20 | 6.0 seconds20 | 30 damage \+ 2.5s–4.0s Concuss20 |
| **Breach** | Fault Line | Indestructible15 | 1.1s Windup20 | 2.5s Concuss debuff20 |

### **Sova**

Sova uses his custom bow and flying drone to gather information and attack targets through cover13.

* **Owl Drone (C)**: Cost: 400 Credits | Max Charges: 1 | Drone HP: 100 HP | Flight Uptime: 7.0s | Dart Cooldown: 5.0s13. Deploys a steerable drone capable of firing marking darts that reveal struck enemies13.  
* **Shock Bolt (Q)**: Cost: 150 Credits | Max Charges: 2 | Max Bounces: 2 | Damage: 1 to 75 HP (scaling from outer splash radius to epicenter)13. Fires an explosive arrow that detonates on collision13.  
* **Recon Bolt (E \- Signature)**: Cost: Free | Max Charges: 1 | Health: 20 HP | Cooldown: 60s | Scanning Radius: 30.0m | Active Duration: 3.2s (2 sonar pulses spaced 1.6s apart)13. Launches an arrow that pulses sonar waves, revealing line-of-sight targets for 0.75 seconds per ping13.  
* **Hunter's Fury (X \- Ultimate)**: Cost: 8 Ultimate Points | Blasts: 3 energy beams | Cast Window: 6.0s | Damage: 80 HP per blast | Debuff: 1.0s real-time reveal13. Fires up to three wall-piercing energy blasts13.

### **Fade**

Fade channels fear essence to track down targets and inflict severe debuffs12.

* **Prowler (C)**: Cost: 250 Credits | Max Charges: 2 | Creature HP: 60 HP | Duration: 2.5s | Debuff: 2.75s Nearsight12. Releases a creature that locks onto targets or Terror Trails, chasing them down to apply Nearsight12.  
* **Seize (Q)**: Cost: 200 Credits | Max Charges: 1 | Active Tether Duration: 4.5s | Debuff: Deafen, Tether, and 75 HP Decay (restored over 5.0s)12. Throws a fear knot that drops to the floor, tethering enemies and decaying their HP12.  
* **Haunt (E \- Signature)**: Cost: Free | Max Charges: 1 | Watcher HP: 1 HP | Cooldown: 60s | Active Spotting Duration: 1.5s | Debuff: Real-time reveal \+ 12.0s Terror Trail12. Throws an orb that drops to form a watcher, revealing line-of-sight targets and tracing Terror Trails to them12.  
* **Nightfall (X \- Ultimate)**: Cost: 8 Ultimate Points12. Sends out a wave of nightmare energy through terrain, applying Decay, Deafen, and a 12-second Terror Trail to caught targets12.

### **Breach**

Breach fires seismic shockwaves directly through terrain to daze and blind defenders15.

* **Aftershock (C)**: Cost: 200 Credits | Max Charges: 1 | Radius: 3.0 m | Function: Wall-piercing explosive charge delivering 2 heavy pulses. *Corrected 28 August 2026 against wiki.playvalorant.com and Riot's own patch notes: this said three pulses, and v7.04 cut the ticks 3 >>> 2 while raising damage 60 >>> 80. The radius is Riot's, from patch v3.0 -- "Explosion radius increased 260 >>> 300" -- and the blast is a cylinder roughly 10 m long projected in front of the wall rather than a sphere, so the 3.0 m is its radius and not its extent.*  
* **Flashpoint (Q)**: Cost: 250 Credits | Max Charges: 2 | Function: Wall-piercing flash burst blinding players on the far side4.  
* **Fault Line (E \- Signature)**: Cost: Free | Max Charges: 1 | Windup Delay: 1.1s | Cooldown: 60s | Debuff: 2.5s Concuss20. Fires a straight seismic quake through terrain, concussing caught targets20.  
* **Rolling Thunder (X \- Ultimate)**: Cost: 8 Ultimate Points | Function: Large directional quake that knocks enemies airborne and concusses them15.

### **Skye**

Skye summons beasts to scout areas, concuss enemies, and heal allies15.

* **Regrowth (C)**: Cost: 150 Credits | Max Pool: 100 Health Points | Function: Area-of-effect heal for allies within line of sight (does not heal self)4.  
* **Trailblazer (Q)**: Cost: 300 Credits | Max Charges: 1 | Creature HP: 80 HP | Duration: 6.0s | Direct Damage: 30 HP | Debuff: 2.5s–4.0s Concuss20. Controls a Tasmanian tiger that leaps forward to explode into a concussive blast20.  
* **Guiding Light (E \- Signature)**: Cost: Free | Max Charges: 1 | Function: Steerable hawk projectile detonating into a flash4.  
* **Seekers (X \- Ultimate)**: Cost: 8 Ultimate Points | Seekers: 3 target-tracking trinkets | Debuff: Nearsights targets upon contact4.

## **Duelist Class: Kinetic Entry Mechanics and Frag Execution**

Duelists focus on taking initial entry engagements, securing kills, and creating space for their team2.

| Agent | Signature Ability | Signature Recharge Trigger | Mobility / Key Mechanic | Ultimate Cost |
| :---- | :---- | :---- | :---- | :---- |
| **Jett** | Tailwind | 2 Kills in round14 | 0.45s directional dash14 | 8 Ultimate Points14 |
| **Phoenix** | Hot Hands | 2 Kills in round29 | Molotov \+ self-healing19 | 6 Ultimate Points30 |
| **Reyna** | Devour / Dismiss | 2 Kills (requires Soul Orbs)22 | Overhealing / Intangibility22 | 8 Ultimate Points15 |
| **Raze** | Paint Shells | 2 Kills in round4 | Cluster explosive burst25 | 8 Ultimate Points25 |

### **Jett**

Jett relies on evasive mobility and airborne angles to catch defenders off guard14.

* **Drift (Passive)**: Holding the jump button glides slowly through the air14.  
* **Cloudburst (C)**: Cost: 200 Credits | Max Charges: 2 | Active Duration: 2.5s14. Throws a fast smoke projectile that expands into a brief vision-blocking cloud14.  
* **Updraft (Q)**: Cost: 150 Credits | Max Charges: 1 | Windup Delay: 0.6s14. Propels Jett high into the air14.  
* **Tailwind (E \- Signature)**: Cost: Free | Max Charges: 1 (Recharges on 2 kills) | Priming Window: 7.5s | Dash Duration: 0.45s | Activation Delay: 1.0s14. Prepares a gust of wind, allowing Jett to dash instantly in her direction of movement14.  
* **Blade Storm (X \- Ultimate)**: Cost: 8 Ultimate Points | Daggers: 5 accurate throwing knives | Damage: 150 (Head), 50 (Body), 42 (Legs)14. Primary fire throws a single knife (recharging all daggers on a kill); alternate fire throws all remaining daggers without recharging14.

### **Phoenix**

Phoenix uses fire utility to heal himself while damaging enemies and blinding positions19.

* **Heating Up (Passive)**: Standing in his own flames heals Phoenix for up to 50 HP over the full duration19.  
* **Blaze (C)**: Cost: 150 Credits | Max Charges: 1 | Duration: \~8.0s | Healing Rate: 1 HP per 0.16s16. Erects a wall of flame that blocks vision, damages enemies, and heals Phoenix16.  
* **Curveball (Q)**: Cost: 250 Credits | Max Charges: 2 | Function: Curved flare orb blinding players around corners4.  
* **Hot Hands (E \- Signature)**: Cost: 200 Credits | Max Charges: 1 (Recharges on 2 kills) | Healing Rate: 1 HP per 0.08s19. Throws a fireball that creates a localized healing/damage flame patch19.  
* **Run it Back (X \- Ultimate)**: Cost: 6 Ultimate Points | Duration: \~10.0s30. Places a marker and spawns a clone; if Phoenix dies or the timer expires, he respawns at the marker with full health30.

### **Reyna**

Reyna thrives in isolated 1v1 duels, using Soul Orbs dropped by killed enemies to empower her abilities22.

* **Soul Harvest (Passive)**: Enemies killed by Reyna drop a Soul Orb lasting 3.0 seconds19.  
* **Leer (C)**: Cost: 250 Credits | Max Charges: 2 | Health: 100 HP | Debuff: Nearsights enemies looking directly at the eye4.  
* **Devour (Q)**: Cost: 100 Credits | Max Charges: 2 (Shared pool with Dismiss) | Function: Consumes a Soul Orb to rapidly heal up to \+50 Overheal HP4.  
* **Dismiss (E \- Signature)**: Cost: 100 Credits | Max Charges: 2 (Shared pool with Devour) | Function: Consumes a Soul Orb to become intangible for 2 seconds (invisible during Ultimate)4.  
* **Empress (X \- Ultimate)**: Cost: 8 Ultimate Points | Duration: \~30s (resets on kill)4. Grants Combat Stim (increased fire rate, reload, and swap speed) and automatically casts Devour on kills4.

### **Raze**

Raze uses heavy explosives to clear corners and deal area-of-effect damage25.

* **Boom Bot (C)**: Cost: 300 Credits | Max Charges: 1 | Health: 60 HP4. Deploys a ground bot that bounces off walls, locking onto and chasing enemies to explode25.  
* **Blast Pack (Q)**: Cost: 200 Credits | Max Charges: 2 | Function: Sticky satchel charge that can be detonated remotely to boost Raze or displace enemies4.  
* **Paint Shells (E \- Signature)**: Cost: Free | Max Charges: 1 (Recharges on 2 kills) | Function: Cluster grenade dealing initial damage before splitting into 4 secondary sub-munitions4.  
* **Showstopper (X \- Ultimate)**: Cost: 8 Ultimate Points | Function: Equips a rocket launcher dealing heavy area-of-effect impact damage25.

## **Cross-Class Tactical Interactions and Quantitative Ability Dynamics**

The strategic execution of VALORANT ability kits relies on mathematical interactions between smoke durations, utility health pools, and debuff stacking7.  
Smoke uptime directly impacts offensive site executions and defensive delay tactics7. Brimstone's Sky Smoke provides an uninterrupted uptime of 19.25 seconds—the longest static smoke duration in the game—making it effective for single-burst site takes where defenders are completely cut off for nearly half of the 45-second Spike fuse timer16. Conversely, Controllers with renewable smokes (Omen on a 40-second cooldown9, Astra on 35 seconds8, and Clove on 40 seconds17) excel during drawn-out mid-map defaults. However, Clove's post-death Ruse drops from a 14-second active duration down to just 6 seconds, creating a tight 6-second window for surviving teammates to capitalize on vision denial17.  
Combining multiplicative debuffs across different agent classes allows teams to execute instant-kill setups without requiring headshots8. For example, Clove's Meddle applies a 90 HP Decay debuff, dropping a full 150 HP armored target down to 60 HP17. If paired with a Sova Shock Bolt (which deals up to 75 damage), any target caught within the overlap dies instantly13. Similarly, Astra's Gravity Well applies a 2.5-second Vulnerable status, doubling incoming damage8. When combined with Brimstone's Incendiary (which deals 60 base DPS), the effective damage tick rate spikes to 120 DPS, melting an armored target in under 1.25 seconds8.  
Deployable utility health pools force attackers and defenders into quick economic trade-offs regarding magazine consumption and crosshair placement10.

| Deployable Object | Object HP | Required Body Shots (Vandal \- 40 Dmg) | Tactical Ammo & Crosshair Trade-Off |
| :---- | :---- | :---- | :---- |
| **Fade Haunt** | 1 HP12 | 1 Bullet | Instant destruction; minor crosshair adjustment12. |
| **Cypher Trapwire** | 20 HP26 | 1 Bullet | Disables tether before reveal triggers26. |
| **Chamber Trademark** | 20 HP11 | 1 Bullet | Prevents slow field activation11. |
| **Sova Recon Bolt** | 20 HP13 | 1 Bullet | Destroys arrow before second sonar scan13. |
| **Killjoy Alarmbot** | 20 HP10 | 1 Bullet | Prevents Vulnerable debuff application10. |
| **Chamber Anchor** | 50 HP11 | 2 Bullets | Requires deliberate recoil control adjustment11. |
| **Fade Prowler** | 60 HP12 | 2 Bullets | Consumes ammo during entry rush12. |
| **Skye Trailblazer** | 80 HP20 | 2 Bullets | Requires multi-hit tracking fire20. |
| **Killjoy Turret** | 100 HP10 | 3 Bullets | Consumes 12% of rifle magazine10. |
| **Sova Owl Drone** | 100 HP13 | 3 Bullets | Exposes position and draws crosshair up13. |
| **Killjoy Lockdown** | 200 HP10 | 5 Bullets | Requires sustained weapon fire or damage utility10. |

Shooting down a 100 HP Sova Drone or Killjoy Turret requires three body shots from a standard Vandal (dealing 40 damage per bullet)10. This consumes 12% of a standard 25-round magazine, reveals the defender's firing position through gun audio, and pulls their crosshair away from main choke points, opening entry paths for Duelists2.

## **Strategic Conclusions**

Site executions and post-plant setups rely on matching utility timings with team strategies7. Brimstone's 19.25-second smokes provide effective single-burst coverage for rapid site takes, whereas Omen and Astra offer higher value during drawn-out mid-map defaults due to their renewable 40s and 35s smoke cycles8.  
Sentinel deployables (such as Killjoy's Turret and Alarmbot or Chamber's Trademark) represent major economic investments that should be recalled when rotating10. Recalling undamaged utility resets them to 20-to-30-second cooldowns, keeping defensive utility active across shifting round conditions10.  
Finally, combining recon tools (such as Sova's Recon Bolt or Fade's Haunt) with wall-piercing area-denial utility (like Breach's Aftershock or Sova's Hunter's Fury) allows teams to clear high-risk defensive positions safely without risking early direct rifle duels12.

#### **Works cited**

> 1. Agents \- VALORANT, [https://playvalorant.com/en-us/agents/](https://playvalorant.com/en-us/agents/)  
> 2. Agents \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Agents](https://valorant.fandom.com/wiki/Agents)  
> 3. Portal:Agents \- Liquipedia VALORANT Wiki, [https://liquipedia.net/valorant/Portal:Agents](https://liquipedia.net/valorant/Portal:Agents)  
> 4. Abilities \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Abilities](https://valorant.fandom.com/wiki/Abilities)  
> 5. Full list of abilities, prices, cooldowns and passives : r/VALORANT, [https://www.reddit.com/r/VALORANT/comments/hk75fu/full\_list\_of\_abilities\_prices\_cooldowns\_and/](https://www.reddit.com/r/VALORANT/comments/hk75fu/full_list_of_abilities_prices_cooldowns_and/)  
> 6. Full info about the agent\`s abilities : r/VALORANT \- Reddit, [https://www.reddit.com/r/VALORANT/comments/gtncrb/full\_info\_about\_the\_agents\_abilities/](https://www.reddit.com/r/VALORANT/comments/gtncrb/full_info_about_the_agents_abilities/)  
> 7. Valorant Agent Abilities Guide: Roles, Skills and Counters for Ranked, [https://amber.gg/blog/valorant/valorant-agent-abilities-guide](https://amber.gg/blog/valorant/valorant-agent-abilities-guide)  
> 8. Astra \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Astra](https://valorant.fandom.com/wiki/Astra)  
> 9. Omen \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Omen](https://valorant.fandom.com/wiki/Omen)  
> 10. [https://valorant.fandom.com/wiki/Killjoy](https://valorant.fandom.com/wiki/Killjoy)  
> 11. Chamber \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Chamber](https://valorant.fandom.com/wiki/Chamber)  
> 12. Fade \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Fade](https://valorant.fandom.com/wiki/Fade)  
> 13. Sova \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Sova](https://valorant.fandom.com/wiki/Sova)  
> 14. [https://valorant.fandom.com/wiki/Jett](https://valorant.fandom.com/wiki/Jett)  
> 15. Characters in Valorant \- TV Tropes, [https://tvtropes.org/pmwiki/pmwiki.php/Characters/Valorant](https://tvtropes.org/pmwiki/pmwiki.php/Characters/Valorant)  
> 16. Brimstone \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Brimstone](https://valorant.fandom.com/wiki/Brimstone)  
> 17. Clove \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Clove](https://valorant.fandom.com/wiki/Clove)  
> 18. Orbital Strike \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Orbital\_Strike](https://valorant.fandom.com/wiki/Orbital_Strike)  
> 19. Passive Effects \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Passive\_Effects](https://valorant.fandom.com/wiki/Passive_Effects)  
> 20. Crowd Control \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Crowd\_Control](https://valorant.fandom.com/wiki/Crowd_Control)  
> 21. [https://valorant.fandom.com/wiki/Viper](https://valorant.fandom.com/wiki/Viper)  
> 22. Abilities \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/id/wiki/Abilities](https://valorant.fandom.com/id/wiki/Abilities)  
> 23. Chamber \- Liquipedia VALORANT Wiki, [https://liquipedia.net/valorant/Chamber](https://liquipedia.net/valorant/Chamber)  
> 24. Sage \- Liquipedia VALORANT Wiki, [https://liquipedia.net/valorant/Sage](https://liquipedia.net/valorant/Sage)  
> 25. All Valorant agents: Abilities, backgrounds, release dates, [https://www.oneesports.gg/valorant/all-valorant-agents-abilities/](https://www.oneesports.gg/valorant/all-valorant-agents-abilities/)  
> 26. Cypher \- Liquipedia VALORANT Wiki, [https://liquipedia.net/valorant/Cypher](https://liquipedia.net/valorant/Cypher)  
> 27. Recon Bolt \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Recon\_Bolt](https://valorant.fandom.com/wiki/Recon_Bolt)  
> 28. Owl Drone \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Owl\_Drone](https://valorant.fandom.com/wiki/Owl_Drone)  
> 29. Valorant: Agents guide \- All Abilities explained | Rock Paper Shotgun, [https://www.rockpapershotgun.com/valorant-agents-guide-all-abilities-explained](https://www.rockpapershotgun.com/valorant-agents-guide-all-abilities-explained)  
> 30. Valorant Agent Abilities By The Numbers \- Reddit, [https://www.reddit.com/r/ValorantCompetitive/comments/g7dyxb/valorant\_agent\_abilities\_by\_the\_numbers/](https://www.reddit.com/r/ValorantCompetitive/comments/g7dyxb/valorant_agent_abilities_by_the_numbers/)  
> 31. Patch Notes/5.12 \- Valorant Wiki \- Fandom, [https://valorant.fandom.com/wiki/Patch\_Notes/5.12](https://valorant.fandom.com/wiki/Patch_Notes/5.12)