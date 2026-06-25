Après avoir regarder la structure du projet dans le repertoire /doc


1/ Modifie la liste des adhérents /entities/members selon les consignes ci-dessous :
- ajoute une colonne 'Date anniversaire' ( méthode "member_birthday" )
- ajoute une colonne 'Status' ( methode "member_status" affiché sous forme de pills de couleur "color" avec le label "status" )
- rend la liste triable selon 3 colonnes (Nom, Date anniversaire, Status)

2/ Ajoute un selecteur sur l'export avec un choix de format (CSV, XSL, XSLX)

3/ Modifie la méthode d'export /entities/members.csv pour les 3 formats selon les consignes ci-dessous :
- intégre les 2 méthodes avec trois attributs (member_birthday, member_status[:status], member_status[:color])

4/ Ajoute une fonctionnalité de relance des adhérents (par email) dont la date d'anniversaire est depassé (member_status[:status] == :red)
- ajoute le paramétrage SMTP dans .env
- ajoute un modele d'email modifiable avec l'intégration d'un lien vers HelloAsso pour renouveller son adhésion


# Details de la méthode "member_birthday"

Calcul de la date anniversaire

- Si Dernière adhésion HA est vide ou null && Dernière adhésion POS est vide ou null
> Date du jour

- Si Dernière adhésion HA est vide ou null && Dernière adhésion POS presente
> Dernière adhésion POS + 365 jours

- Si Dernière adhésion HA presente && Dernière adhésion POS presente
> Date la plus recente + 365 jours

# Details de la méthode "member_status"

Renvoie un hash { status: status, color: color }  selon des conditions suivantes

pour color
- Si member_birthday <= Date.now 
> :green

- Si member_birthday > Date.now 
> :red

- Si member_birthday <= Date.now + 30 jours
> :orange

pour status
- Si Dernière adhésion HA est vide ou null && Dernière adhésion POS est vide ou null
> "?"
- Si Dernière adhésion HA est vide ou null && Dernière adhésion POS presente
> "asha"
- Sinon
> "ok"