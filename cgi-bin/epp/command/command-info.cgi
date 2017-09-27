#!/usr/bin/perl

###############################################################################
#
#	-------------------------
#			XPanel EPP Server
#		-------------------------
#
#	Version: 1.0.0
#	Web Site: http://www.xpanel.com/
#
#	(c) Copyright 2017 XPanel Ltd.
#
# *  XPanel Ltd. licenses this file to You under the Apache License, Version 2.0
# *  (the "License"); you may not use this file except in compliance with
# *  the License.  You may obtain a copy of the License at
# *
# *      http://www.apache.org/licenses/LICENSE-2.0
# *
# *  Unless required by applicable law or agreed to in writing, software
# *  distributed under the License is distributed on an "AS IS" BASIS,
# *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
###############################################################################



use lib '/var/www/cgi-bin/epp/lib';
use strict;
use warnings;
use EPP::Config();
use EPP::EPPWriter;
use CGI qw(:standard);
use XML::XPath;
use DBI;
use EPP::Date qw(:all);
use vars qw(%c $dbh $q);
*c = \%EPP::Config::c;
$q = new CGI;
$dbh = DBI->connect("DBI:mysql:$c{'mysql_database'}:$c{'mysql_host'}:$c{'mysql_port'}","$c{'mysql_username'}","$c{'mysql_password'}") or die "$DBI::errstr";

print header('application/epp+xml');

my $frame = $q->param('frame');
my $xp = XML::XPath->new(xml => $frame);

my $cltrid = $q->param('clTRID');
$cltrid = 'not-given' unless (defined($cltrid));
my $remote_user = $ENV{REMOTE_USER};


$xp->set_namespace('epp', 'urn:ietf:params:xml:ns:epp-1.0');
$xp->set_namespace('contact', 'urn:ietf:params:xml:ns:contact-1.0');
$xp->set_namespace('domain', 'urn:ietf:params:xml:ns:domain-1.0');
$xp->set_namespace('host', 'urn:ietf:params:xml:ns:host-1.0');
	$xp->set_namespace('balance', 'http://www.verisign.com/epp/balance-1.0');

my $blob = {};
$blob->{clTRID} = $cltrid;
$blob->{resultCode} = 1000;
$blob->{cmd} = 'info';

my $node = $xp->findnodes('/epp:epp/epp:command/epp:info')->get_node(0);
my ($registrar_id,$accountBalance,$creditLimit,$creditThreshold,$thresholdType) = $dbh->selectrow_array("SELECT `id`,`accountBalance`,`creditLimit`,`creditThreshold`,`thresholdType` FROM `registrar` WHERE `clid` = '$remote_user' LIMIT 1");

my $sth = $dbh->prepare("INSERT INTO `registryTransaction`.`transaction_identifier` (`registrar_id`,`clTRID`,`clTRIDframe`,`cldate`,`clmicrosecond`) VALUES(?,?,?,?,?)") or die $dbh->errstr;
my $date_for_cl_transaction = microsecond();
my ($cldate,$clmicrosecond) = split(/\./, $date_for_cl_transaction);
$sth->execute($registrar_id,$cltrid,$frame,$cldate,$clmicrosecond) or die $sth->errstr;
my $transaction_id = $dbh->last_insert_id(undef, undef, undef, undef);

my $obj;
if ($obj = $xp->find('contact:info',$node)->get_node(0)) {
	################################################################
	#
	#			<info><contact:id>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-contact:info';
	$blob->{command} = 'info_contact';
	$blob->{obj_type} = 'contact';

	# -  A <contact:id> element that contains the server-unique identifier of the contact object to be queried.
	my $identifier = $xp->findvalue('contact:id[1]', $obj);
	$blob->{obj_id} = $identifier;

	my $authInfo_pw = $xp->findvalue('contact:authInfo/contact:pw[1]', $obj);
	my $authInfo_ext = $xp->findvalue('contact:authInfo/contact:ext[1]', $obj);

	if (!$identifier) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Indica contact ID';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	$identifier = uc($identifier);
	my $invalid_identifier = validate_identifier($identifier);
	if ($invalid_identifier) {
		$blob->{resultCode} = 2005; # Parameter value syntax error
		$blob->{human_readable_message} = $invalid_identifier;
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:contact';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:contact-1.0';
			$blob->{obj_elem} = 'contact:id';
			$blob->{obj_elem_value} = $identifier;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my ($contact_id,$voice,$voice_x,$fax,$fax_x,$email,$nin,$nin_type,$registrar_id_contact,$crid,$crdate,$upid,$update,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$disclose_voice,$disclose_fax,$disclose_email) = $dbh->selectrow_array("SELECT `id`,`voice`,`voice_x`,`fax`,`fax_x`,`email`,`nin`,`nin_type`,`clid`,`crid`,`crdate`,`upid`,`update`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`disclose_voice`,`disclose_fax`,`disclose_email` FROM `contact` WHERE `identifier` = '$identifier' LIMIT 1");
	if (!$contact_id) {
		$blob->{resultCode} = 2303; # Object does not exist
		$blob->{human_readable_message} = 'Nu exista asa contact';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	# This element MUST NOT be provided if the querying client is not the current sponsoring client
	# ********************
	if ($registrar_id == $registrar_id_contact) {
		$blob->{authInfo} = 'valid';
		my ($authtype,$authinfo) = $dbh->selectrow_array("SELECT `authtype`,`authinfo` FROM `contact_authInfo` WHERE `contact_id` = '$contact_id' AND `authtype` = 'pw' LIMIT 1");
		$blob->{authInfo_type} = $authtype;
		$blob->{authInfo_val} = $authinfo;
	}
	else {
		my ($authtype,$authinfo) = $dbh->selectrow_array("SELECT `authtype`,`authinfo` FROM `contact_authInfo` WHERE `contact_id` = '$contact_id' AND `authtype` = 'pw'  AND `authinfo` = '$authInfo_pw' LIMIT 1");
		if ($authtype) {
			$blob->{authInfo} = 'valid';
			$blob->{authInfo_type} = $authtype;
			$blob->{authInfo_val} = $authinfo;
		}
		else {
			$blob->{authInfo} = 'invalid';
		}
	}
	# ********************

	$blob->{id} = $identifier;
	$blob->{roid} = 'C_' . $contact_id . '-' . $c{'repository'};
	$blob->{status} = [ ];

	my ($count_status) = $dbh->selectrow_array("SELECT COUNT(`id`) FROM `contact_status` WHERE `contact_id` = '$contact_id'") or die $dbh->errstr;
	if ($count_status > 0) {
		my $sth = $dbh->prepare("SELECT `status` FROM `contact_status` WHERE `contact_id` = ?") or die $dbh->errstr;
		$sth->execute($contact_id) or die $sth->errstr;
		while (my $status = $sth->fetchrow_array()) {
			push (@{$blob->{status}}, [ $status, 'en-US', $status ]); # de revizuit aici cu languages ?
		}
		$sth->finish;
	}
	else {
		push (@{$blob->{status}}, [ 'ok', 'en-US', 'ok' ]); # de revizuit aici cu languages ?
	}

	my ($is_linked) = $dbh->selectrow_array("SELECT `domain_id` FROM `domain_contact_map` WHERE `contact_id` = '$contact_id' LIMIT 1");
	if ($is_linked) {
		push (@{$blob->{status}}, [ 'linked', 'en-US', 'linked' ]); # de revizuit aici cu languages ?
	}

	$sth = $dbh->prepare("SELECT `type`,`name`,`org`,`street1`,`street2`,`street3`,`city`,`sp`,`pc`,`cc`,`disclose_name_int`,`disclose_name_loc`,`disclose_org_int`,`disclose_org_loc`,`disclose_addr_int`,`disclose_addr_loc` FROM `contact_postalInfo` WHERE `contact_id` = ?") or die $dbh->errstr;
	$sth->execute($contact_id) or die $sth->errstr;
	while (my ($type,$name,$org,$street1,$street2,$street3,$city,$sp,$pc,$cc,$disclose_name_int,$disclose_name_loc,$disclose_org_int,$disclose_org_loc,$disclose_addr_int,$disclose_addr_loc) = $sth->fetchrow_array()) {
		$blob->{postal}->{$type}->{name} = $name;
		$blob->{postal}->{$type}->{org} = $org;
		$blob->{postal}->{$type}->{street} = [ $street1,$street2,$street3 ];
		$blob->{postal}->{$type}->{city} = $city;
		$blob->{postal}->{$type}->{sp} = $sp;
		$blob->{postal}->{$type}->{pc} = $pc;
		$blob->{postal}->{$type}->{cc} = $cc;
	}
	$sth->finish;

	$blob->{voice} = $voice if ($voice);
	$blob->{voice_x} = $voice_x if ($voice_x);
	$blob->{fax} = $fax if ($fax);
	$blob->{fax_x} = $fax_x if ($fax_x);
	$blob->{email} = $email;
	$blob->{nin} = $nin;
	$blob->{nin_type} = $nin_type;
	$blob->{clID} = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$registrar_id_contact' LIMIT 1");
	$blob->{crID} = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$crid' LIMIT 1");
	$crdate =~ s/\s/T/g;
	$crdate .= '.0Z';
	$blob->{crDate} = $crdate;
	if ($upid) {
		$blob->{upID} = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$upid' LIMIT 1");
	}
	if ($update) {
		$update =~ s/\s/T/g;
		$update .= '.0Z';
		$blob->{upDate} = $update;
	}
	if ($trdate) {
		$trdate =~ s/\s/T/g;
		$trdate .= '.0Z';
		$blob->{trDate} = $trdate;
	}

	# An OPTIONAL <contact:disclose> de revizuit si de determinat cu politica disclose, de vazut la altii cum este
	# de exemplu la .uk asa ceva se ignora, mi se pare ca si la .no asa ceva se ignora

	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
elsif ($obj = $xp->find('domain:info',$node)->get_node(0)) {
	################################################################
	#
	#			<info><domain:name>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-domain:info';
	$blob->{command} = 'info_domain';
	$blob->{obj_type} = 'domain';

	# -  A <domain:name> element that contains the fully qualified name of the domain object to be queried.
	my $name = $xp->findvalue('domain:name[1]', $obj);
	$blob->{obj_id} = $name;

	my $hosts = $xp->findvalue('domain:name/@hosts[1]', $obj);
	if (!$hosts) {
		$hosts = 'all';
	}

	if ($hosts eq 'all') {
		$blob->{return_ns} = 1;
		$blob->{return_host} = 1;
	}
	elsif ($hosts eq 'del') {
		$blob->{return_ns} = 1;
		$blob->{return_host} = 0;
	}
	elsif ($hosts eq 'sub') {
		$blob->{return_ns} = 0;
		$blob->{return_host} = 1;
	}
	elsif ($hosts eq 'none') {
		$blob->{return_ns} = 0;
		$blob->{return_host} = 0;
	}
	else {
		$blob->{return_ns} = 1;
		$blob->{return_host} = 1;
	}

	my $authInfo_pw = $xp->findvalue('domain:authInfo/domain:pw[1]', $obj);
	my $authInfo_pw_roid = $xp->findvalue('domain:authInfo/domain:pw/@roid[1]', $obj);
	my $authInfo_ext = $xp->findvalue('domain:authInfo/domain:ext[1]', $obj);
	my $authInfo_ext_roid = $xp->findvalue('domain:authInfo/domain:ext/@roid[1]', $obj);

	if (!$name) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Indica numele de domeniu';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	$name = uc($name);
	my ($label,$domain_extension) = $name =~ /^([^\.]+)\.(.+)$/;
	my $invalid_domain = validate_label($label);

	if ($invalid_domain) {
		$blob->{resultCode} = 2306; # Parameter value policy error
		$blob->{human_readable_message} = 'Invalid domain:name';
			$blob->{optionalValue} = 1;
			$blob->{xmlns_obj} = 'xmlns:domain';
			$blob->{xmlns_obj_value} = 'urn:ietf:params:xml:ns:domain-1.0';
			$blob->{obj_elem} = 'domain:name';
			$blob->{obj_elem_value} = $name;
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	my ($domain_id,$registrant,$crdate,$exdate,$update,$registrar_id_domain,$crid,$upid,$trdate,$trstatus,$reid,$redate,$acid,$acdate,$rgpstatus) = $dbh->selectrow_array("SELECT `id`,`registrant`,`crdate`,`exdate`,`update`,`clid`,`crid`,`upid`,`trdate`,`trstatus`,`reid`,`redate`,`acid`,`acdate`,`rgpstatus` FROM `domain` WHERE `name` = '$name' LIMIT 1");
	if (!$domain_id) {
		$blob->{resultCode} = 2303; # Object does not exist
		$blob->{human_readable_message} = 'Nu exista asa domeniu';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	# This element MUST NOT be provided if the querying client is not the current sponsoring client
	# ********************
	if ($registrar_id == $registrar_id_domain) {
		$blob->{authInfo} = 'valid';
		my ($authtype,$authinfo) = $dbh->selectrow_array("SELECT `authtype`,`authinfo` FROM `domain_authInfo` WHERE `domain_id` = '$domain_id' AND `authtype` = 'pw' LIMIT 1");
		$blob->{authInfo_type} = $authtype;
		$blob->{authInfo_val} = $authinfo;
	}
	else {
		my ($authtype,$authinfo) = $dbh->selectrow_array("SELECT `authtype`,`authinfo` FROM `domain_authInfo` WHERE `domain_id` = '$domain_id' AND `authtype` = 'pw'  AND `authinfo` = '$authInfo_pw' LIMIT 1");
		if ($authtype) {
			$blob->{authInfo} = 'valid';
			$blob->{authInfo_type} = $authtype;
			$blob->{authInfo_val} = $authinfo;
		}
		else {
			$blob->{authInfo} = 'invalid';
		}
	}
	# ********************

	$blob->{name} = $name;
	$blob->{roid} = 'D_' . $domain_id . '-' . $c{'repository'};
	$blob->{status} = [ ];

	my ($count_status) = $dbh->selectrow_array("SELECT COUNT(`id`) FROM `domain_status` WHERE `domain_id` = '$domain_id'") or die $dbh->errstr;
	if ($count_status > 0) {
		my $sth = $dbh->prepare("SELECT `status` FROM `domain_status` WHERE `domain_id` = ?") or die $dbh->errstr;
		$sth->execute($domain_id) or die $sth->errstr;
		while (my $status = $sth->fetchrow_array()) {
			push (@{$blob->{status}}, [ $status, 'en-US', $status ]); # de revizuit aici cu languages ?
		}
		$sth->finish;
	}
	else {
		push (@{$blob->{status}}, [ 'ok', 'en-US', 'ok' ]); # de revizuit aici cu languages ?
	}

	my ($registrant_identifier) = $dbh->selectrow_array("SELECT `identifier` FROM `contact` WHERE `id` = '$registrant' LIMIT 1");

	$blob->{registrant} = $registrant_identifier;

	$sth = $dbh->prepare("SELECT `contact_id`,`type` FROM `domain_contact_map` WHERE `domain_id` = ?") or die $dbh->errstr;
	$sth->execute($domain_id) or die $sth->errstr;
	while (my ($contact_id,$type) = $sth->fetchrow_array()) {
		my ($identifier) = $dbh->selectrow_array("SELECT `identifier` FROM `contact` WHERE `id` = '$contact_id' LIMIT 1");
		push (@{$blob->{contact}}, [ $type, $identifier ]);
	}
	$sth->finish;

	# aceste 2 selecturi de mai jos pentru :ns si :host mai trebuie verificate conform rfc 5731
	$sth = $dbh->prepare("SELECT `host`.`name` FROM `host`,`domain_host_map`  WHERE `domain_host_map`.`domain_id` = ? AND `domain_host_map`.`host_id` = `host`.`id`") or die $dbh->errstr;
	$sth->execute($domain_id) or die $sth->errstr;
	while (my ($ns) = $sth->fetchrow_array()) {
		push (@{$blob->{hostObj}}, $ns);
	}
	$sth->finish;

	$sth = $dbh->prepare("SELECT `name` FROM `host` WHERE `domain_id` = ?") or die $dbh->errstr;
	$sth->execute($domain_id) or die $sth->errstr;
	while (my ($host) = $sth->fetchrow_array()) {
		push (@{$blob->{host}}, $host);
	}
	$sth->finish;

	$blob->{clID} = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$registrar_id_domain' LIMIT 1");
	$blob->{crID} = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$crid' LIMIT 1");
	$crdate =~ s/\s/T/g;
	$crdate .= '.0Z';
	$blob->{crDate} = $crdate;
	if ($upid) {
		$blob->{upID} = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$upid' LIMIT 1");
	}
	if ($update) {
		$update =~ s/\s/T/g;
		$update .= '.0Z';
		$blob->{upDate} = $update;
	}
	$exdate =~ s/\s/T/g;
	$exdate .= '.0Z';
	$blob->{exDate} = $exdate;
	if ($trdate) {
		$trdate =~ s/\s/T/g;
		$trdate .= '.0Z';
		$blob->{trDate} = $trdate;
	}
	if ($rgpstatus) {
		$blob->{rgpstatus} = $rgpstatus;
	}
	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
elsif ($obj = $xp->find('host:info',$node)->get_node(0)) {
	################################################################
	#
	#			<info><host:name>
	#
	################################################################
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-host:info';
	$blob->{command} = 'info_host';
	$blob->{obj_type} = 'host';

	# -  A <host:name> element that contains the fully qualified name of the host object for which information is requested.
	my $name = $xp->findvalue('host:name[1]', $obj);
	$blob->{obj_id} = $name;

	if (!$name) {
		$blob->{resultCode} = 2003; # Required parameter missing
		$blob->{human_readable_message} = 'Indica hostname';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	$name = uc($name);
	my ($host_id,$domain_id,$registrar_id_host,$crid,$crdate,$upid,$update,$trdate) = $dbh->selectrow_array("SELECT `id`,`domain_id`,`clid`,`crid`,`crdate`,`upid`,`update`,`trdate` FROM `host` WHERE `name` = '$name' LIMIT 1");
	if (!$host_id) {
		$blob->{resultCode} = 2303; # Object does not exist
		$blob->{human_readable_message} = 'Nu este asa hostname';
		my $msg = epp_writer($blob);
		print $msg;
		my $uptr = update_transaction($msg);
		exit;
	}

	$blob->{name} = $name;
	$blob->{roid} = 'H_' . $host_id . '-' . $c{'repository'};
	$blob->{status} = [ ];

	my ($count_status) = $dbh->selectrow_array("SELECT COUNT(`id`) FROM `host_status` WHERE `host_id` = '$host_id'") or die $dbh->errstr;
	if ($count_status > 0) {
		my $sth = $dbh->prepare("SELECT `status` FROM `host_status` WHERE `host_id` = ?") or die $dbh->errstr;
		$sth->execute($host_id) or die $sth->errstr;
		while (my $status = $sth->fetchrow_array()) {
			push (@{$blob->{status}}, [ $status, 'en-US', $status ]); # de revizuit aici cu languages ?
		}
		$sth->finish;
	}
	else {
		push (@{$blob->{status}}, [ 'ok', 'en-US', 'ok' ]); # de revizuit aici cu languages ?
	}

	my ($is_linked) = $dbh->selectrow_array("SELECT `domain_id` FROM `domain_host_map` WHERE `host_id` = '$host_id' LIMIT 1");
	if ($is_linked) {
		push (@{$blob->{status}}, [ 'linked', 'en-US', 'linked' ]); # de revizuit aici cu languages ?
	}

	$sth = $dbh->prepare("SELECT `addr`,`ip` FROM `host_addr` WHERE `host_id` = ?") or die $dbh->errstr;
	$sth->execute($host_id) or die $sth->errstr;
	while (my ($addr, $ip) = $sth->fetchrow_array()) {
		push (@{$blob->{addr}}, [ $ip, $addr ]);
	}
	$sth->finish;

	$blob->{clID} = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$registrar_id_host' LIMIT 1");
	$blob->{crID} = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$crid' LIMIT 1");
	$crdate =~ s/\s/T/g;
	$crdate .= '.0Z';
	$blob->{crDate} = $crdate;
	if ($upid) {
		$blob->{upID} = $dbh->selectrow_array("SELECT `clid` FROM `registrar` WHERE `id` = '$upid' LIMIT 1");
	}
	if ($update) {
		$update =~ s/\s/T/g;
		$update .= '.0Z';
		$blob->{upDate} = $update;
	}
	if ($trdate) {
		$trdate =~ s/\s/T/g;
		$trdate .= '.0Z';
		$blob->{trDate} = $trdate;
	}

	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
elsif ($obj = $xp->find('balance:info',$node)->get_node(0)) {
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-unknown:command';
	$blob->{command} = 'info_balance';
	$blob->{obj_type} = 'balance';

# If a registrar’s available credit reaches zero, the Registry will prohibit the registrar from
# conducting additional billable transactions until its available credit has been replenished. If a
# registrar’s available credit balance falls below zero, then the registrar must replenish its
# account within five days.
# availableCredit = creditLimit - balance
# The low credit threshold is calculated by multiplying the <balance:creditLimit> value with the <balance:percent> percentage value. 

	my $creditBalance = ($accountBalance < 0) ? -$accountBalance : 0;
	my $availableCredit = $creditLimit - $creditBalance;
	$blob->{creditLimit} = $creditLimit + 0;
	$blob->{balance} = $creditBalance;
	$blob->{availableCredit} = $availableCredit;
	$blob->{creditThreshold} = $creditThreshold + 0;
	if ($thresholdType eq 'percent') {
		$blob->{creditThreshold} = int($creditThreshold);
	}
	$blob->{thresholdType} = $thresholdType;

	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}
else {
	my $date_for_svtrid = date_for_svtrid();
	$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-unknown:command';
	$blob->{command} = 'unknown';
	$blob->{resultCode} = 2001;
	$blob->{human_readable_message} = 'comanda necunoscuta';
	my $msg = epp_writer($blob);
	print $msg;
	my $uptr = update_transaction($msg);
}

sub validate_identifier {
	my $identifier = shift;

	if (!$identifier) {
		return "Abstract client and object identifier type minLength value='3'";
	}

	if (length($identifier) < 3) {
		return "Abstract client and object identifier type minLength value='3'";
	}

	if (length($identifier) > 16) {
		return "Abstract client and object identifier type maxLength value='16'";
	}

	if ($identifier =~ /[^A-Z0-9\-]/) {
		return 'Abstract client and object identifier type A-Z0-9-';
	}
}


sub validate_label {
	my $label = shift;
	if (!$label) {
		return 'You must enter a domain name';
	}
	if (length($label) > 63) {
		return 'Total lenght of your domain must be less then 63 characters';
	}
	if (length($label) < 2) {
		return 'Total lenght of your domain must be greater then 2 characters';
	}
	if ($label =~ /[^A-Z0-9\-]/) {
		return 'Invalid domain name format';
	}
	if ($label =~ /^xn--/) {
		if ($label =~ /^-|-$|\.$/) {
			return 'Invalid domain name format, cannot begin or end with a hyphen (-)';
		}
	}
	else {
		if ($label =~ /^-|--|-$|\.$/) {
			return 'Invalid domain name format, cannot begin or end with a hyphen (-)';
		}
	}
}

sub update_transaction {
	my $svframe = shift;
	my $sth = $dbh->prepare("UPDATE `registryTransaction`.`transaction_identifier` SET `cmd` = ?, `obj_type` = ?, `obj_id` = ?, `code` = ?, `msg` = ?, `svTRID` = ?, `svTRIDframe` = ?, `svdate` = ?, `svmicrosecond` = ? WHERE `id` = ?") or die $dbh->errstr;
	my $date_for_sv_transaction = microsecond();
	my ($svdate,$svmicrosecond) = split(/\./, $date_for_sv_transaction);
	$sth->execute($blob->{cmd},$blob->{obj_type},$blob->{obj_id},$blob->{resultCode},$blob->{human_readable_message},$blob->{svTRID},$svframe,$svdate,$svmicrosecond,$transaction_id) or die $sth->errstr;
	return 1;
}