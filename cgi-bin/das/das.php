<?php
$domain = $_GET["domain"];

if (!$domain) die("please enter a domain name");
if (strlen($domain) > 68) die("domain name is too long");
$domain = strtoupper($domain);
if (preg_match("/[^A-Z0-9\.\-]/",$domain)) die("domain name invalid format");
if (preg_match("/(^-|^\.|-\.|\.-|--|\.\.|-$|\.$)/",$domain)) die("domain name invalid format");
if (!preg_match("/^[A-Z0-9-]+\.(XX|COM\.XX|ORG\.XX|INFO\.XX|PRO\.XX)$/",$domain)) die("please search only XX domains at least 2 letter");

$mysqli = new mysqli('localhost', 'registry-select', 'EPPRegistrySELECT','registry') or die('Could not connect');

$r = $mysqli->query("SELECT *,
	DATE_FORMAT(`crdate`, '%d-%b-%Y %T') AS `crdate`,
	DATE_FORMAT(`update`, '%d-%b-%Y %T') AS `update`,
	DATE_FORMAT(`exdate`, '%d-%b-%Y %T') AS `exdate`
	FROM `registry`.`domain` WHERE `name` = '$domain'") or die(mysql_error());

if ($f = $r->fetch_assoc()) {
	if ($f['crdate']) $f['crdate'] .= ' UTC';
	if ($f['update']) $f['update'] .= ' UTC';
	if ($f['exdate']) $f['exdate'] .= ' UTC';

	$r2 = $mysqli->query("SELECT `tld` FROM `domain_tld` WHERE `id` = '{$f['tldid']}'");
	$tld = $r2->fetch_assoc();

	$res = "Access to {$tld['tld']} WHOIS information is provided to assist persons in"
	."\ndetermining the contents of a domain name registration record in the"
	."\nDomain Name Registry registry database. The data in this record is provided by"
	."\nDomain Name Registry for informational purposes only, and Domain Name Registry does not"
	."\nguarantee its accuracy.  This service is intended only for query-based"
	."\naccess. You agree that you will use this data only for lawful purposes"
	."\nand that, under no circumstances will you use this data to: (a) allow,"
	."\nenable, or otherwise support the transmission by e-mail, telephone, or"
	."\nfacsimile of mass unsolicited, commercial advertising or solicitations"
	."\nto entities other than the data recipient's own existing customers; or"
	."\n(b) enable high volume, automated, electronic processes that send"
	."\nqueries or data to the systems of Registry Operator, a Registrar, or"
	."\nNIC except as reasonably necessary to register domain names or"
	."\nmodify existing registrations. All rights reserved. Domain Name Registry reserves"
	."\nthe right to modify these terms at any time. By submitting this query,"
	."\nyou agree to abide by this policy."
	."\n";

	$r2 = $mysqli->query("SELECT `name`,`whois_server`,`url`,`abuse_email`,`abuse_phone` FROM `registrar` WHERE `id` = '{$f['clid']}'");
	$clidF = $r2->fetch_assoc();

	$res .= ""
	."\nRegistry Domain ID:".$f['id']
	."\nDomain Name:".strtoupper($f['name'])
	."\nCreated On:".$f['crdate']
	."\nLast Updated On:".$f['update']
	."\nExpiration Date:".$f['exdate']
	."\nRegistrar:".$clidF['name']
	."\nRegistrar WHOIS Server:".$clidF['whois_server']
	."\nRegistrar URL:".$clidF['url']
	."\nRegistrar Abuse Contact Email:".$clidF['abuse_email']
	."\nRegistrar Abuse Contact Phone:".$clidF['abuse_phone'];
	$r2 = $mysqli->query("SELECT `status` FROM `domain_status` WHERE `domain_id` = '{$f['id']}'");
	while ($f2 = $r2->fetch_assoc()) {
		$res .= "\nStatus:".$f2['status'];
	}

	$r2 = $mysqli->query("SELECT contact.identifier,contact_postalInfo.name,contact_postalInfo.org,contact_postalInfo.street1,contact_postalInfo.street2,contact_postalInfo.street3,contact_postalInfo.city,contact_postalInfo.sp,contact_postalInfo.pc,contact_postalInfo.cc,contact.voice,contact.voice_x,contact.fax,contact.fax_x,contact.email
		FROM contact,contact_postalInfo WHERE contact.id='".$f['registrant']."' AND contact_postalInfo.contact_id=contact.id");
	$f2 = $r2->fetch_assoc();
	$res .= "\nRegistry Registrant ID:".$f2['identifier']
		."\nRegistrant Name:".$f2['name']
		."\nRegistrant Organization:".$f2['org']
		."\nRegistrant Street1:".$f2['street1']
		."\nRegistrant Street2:".$f2['street2']
		."\nRegistrant Street3:".$f2['street3']
		."\nRegistrant City:".$f2['city']
		."\nRegistrant State/Province:".$f2['sp']
		."\nRegistrant Postal Code:".$f2['pc']
		."\nRegistrant Country:".$f2['cc']
		."\nRegistrant Phone:".$f2['voice']
		."\nRegistrant Phone Ext.:".$f2['voice_x']
		."\nRegistrant FAX:".$f2['fax']
		."\nRegistrant FAX Ext.:".$f2['fax_x']
		."\nRegistrant Email:".$f2['email'];

	$r2 = $mysqli->query("SELECT contact.identifier,contact_postalInfo.name,contact_postalInfo.org,contact_postalInfo.street1,contact_postalInfo.street2,contact_postalInfo.street3,contact_postalInfo.city,contact_postalInfo.sp,contact_postalInfo.pc,contact_postalInfo.cc,contact.voice,contact.voice_x,contact.fax,contact.fax_x,contact.email
		FROM domain_contact_map,contact,contact_postalInfo WHERE domain_contact_map.domain_id='".$f['id']."' AND domain_contact_map.type='admin' AND domain_contact_map.contact_id=contact.id AND domain_contact_map.contact_id=contact_postalInfo.contact_id");
	$f2 = $r2->fetch_assoc();
	$res .= "\nRegistry Admin ID:".$f2['identifier']
		."\nAdmin Name:".$f2['name']
		."\nAdmin Organization:".$f2['org']
		."\nAdmin Street1:".$f2['street1']
		."\nAdmin Street2:".$f2['street2']
		."\nAdmin Street3:".$f2['street3']
		."\nAdmin City:".$f2['city']
		."\nAdmin State/Province:".$f2['sp']
		."\nAdmin Postal Code:".$f2['pc']
		."\nAdmin Country:".$f2['cc']
		."\nAdmin Phone:".$f2['voice']
		."\nAdmin Phone Ext.:".$f2['voice_x']
		."\nAdmin FAX:".$f2['fax']
		."\nAdmin FAX Ext.:".$f2['fax_x']
		."\nAdmin Email:".$f2['email'];

	$r2 = $mysqli->query("SELECT contact.identifier,contact_postalInfo.name,contact_postalInfo.org,contact_postalInfo.street1,contact_postalInfo.street2,contact_postalInfo.street3,contact_postalInfo.city,contact_postalInfo.sp,contact_postalInfo.pc,contact_postalInfo.cc,contact.voice,contact.voice_x,contact.fax,contact.fax_x,contact.email
		FROM domain_contact_map,contact,contact_postalInfo WHERE domain_contact_map.domain_id='".$f['id']."' AND domain_contact_map.type='billing' AND domain_contact_map.contact_id=contact.id AND domain_contact_map.contact_id=contact_postalInfo.contact_id");
	$f2 = $r2->fetch_assoc();
	$res .= "\nRegistry Billing ID:".$f2['identifier']
		."\nBilling Name:".$f2['name']
		."\nBilling Organization:".$f2['org']
		."\nBilling Street1:".$f2['street1']
		."\nBilling Street2:".$f2['street2']
		."\nBilling Street3:".$f2['street3']
		."\nBilling City:".$f2['city']
		."\nBilling State/Province:".$f2['sp']
		."\nBilling Postal Code:".$f2['pc']
		."\nBilling Country:".$f2['cc']
		."\nBilling Phone:".$f2['voice']
		."\nBilling Phone Ext.:".$f2['voice_x']
		."\nBilling FAX:".$f2['fax']
		."\nBilling FAX Ext.:".$f2['fax_x']
		."\nBilling Email:".$f2['email'];

	$r2 = $mysqli->query("SELECT contact.identifier,contact_postalInfo.name,contact_postalInfo.org,contact_postalInfo.street1,contact_postalInfo.street2,contact_postalInfo.street3,contact_postalInfo.city,contact_postalInfo.sp,contact_postalInfo.pc,contact_postalInfo.cc,contact.voice,contact.voice_x,contact.fax,contact.fax_x,contact.email
		FROM domain_contact_map,contact,contact_postalInfo WHERE domain_contact_map.domain_id='".$f['id']."' AND domain_contact_map.type='tech' AND domain_contact_map.contact_id=contact.id AND domain_contact_map.contact_id=contact_postalInfo.contact_id");
	$f2 = $r2->fetch_assoc();
	$res .= "\nRegistry Tech ID:".$f2['identifier']
		."\nTech Name:".$f2['name']
		."\nTech Organization:".$f2['org']
		."\nTech Street1:".$f2['street1']
		."\nTech Street2:".$f2['street2']
		."\nTech Street3:".$f2['street3']
		."\nTech City:".$f2['city']
		."\nTech State/Province:".$f2['sp']
		."\nTech Postal Code:".$f2['pc']
		."\nTech Country:".$f2['cc']
		."\nTech Phone:".$f2['voice']
		."\nTech Phone Ext.:".$f2['voice_x']
		."\nTech FAX:".$f2['fax']
		."\nTech FAX Ext.:".$f2['fax_x']
		."\nTech Email:".$f2['email'];

	$r2 = $mysqli->query("SELECT `name` FROM `domain_host_map`,`host` WHERE `domain_host_map`.`domain_id` = '{$f['id']}' AND `domain_host_map`.`host_id` = `host`.`id`");
	for ($i=0; $i<13; $i++) {
		$f2 = $r2->fetch_assoc();
		$res .= "\nName Server:".$f2['name'];
	}

	$res .= "\nDNSSEC:Unsigned";
	$res .= "\n\n";
	echo $res;

	if ($fp = @fopen("/var/log/whois/whois.log",'a')) {
		fwrite($fp,date('Y-m-d H:i:s')."\t-\t".getenv('REMOTE_ADDR')."\t-\t".$domain."\n");
		fclose($fp);
	}
}
else {
	//echo 'No match for';
	echo 'NOT FOUND';

	if ($fp = @fopen("/var/log/whois/whois_not_found.log",'a')) {
		fwrite($fp,date('Y-m-d H:i:s')."\t-\t".getenv('REMOTE_ADDR')."\t-\t".$domain."\n");
		fclose($fp);
	}
}
?>