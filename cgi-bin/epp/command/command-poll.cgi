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

my $blob = {};
$blob->{clTRID} = $cltrid;
$blob->{resultCode} = 1000;
$blob->{cmd} = 'poll';

my $node = $xp->findnodes('/epp:epp/epp:command/epp:poll')->get_node(0);
my ($registrar_id) = $dbh->selectrow_array("SELECT `id` FROM `registrar` WHERE `clid` = '$remote_user' LIMIT 1");

my $sth = $dbh->prepare("INSERT INTO `registryTransaction`.`transaction_identifier` (`registrar_id`,`clTRID`,`clTRIDframe`,`cldate`,`clmicrosecond`) VALUES(?,?,?,?,?)") or die $dbh->errstr;
my $date_for_cl_transaction = microsecond();
my ($cldate,$clmicrosecond) = split(/\./, $date_for_cl_transaction);
$sth->execute($registrar_id,$cltrid,$frame,$cldate,$clmicrosecond) or die $sth->errstr;
my $transaction_id = $dbh->last_insert_id(undef, undef, undef, undef);

my $date_for_svtrid = date_for_svtrid();
$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-epp:poll';

my $op = $node->findvalue('@op[1]');

my ($id,$qdate,$poll_msg,$poll_msg_type,$obj_name_or_id,$obj_trStatus,$obj_reID,$obj_reDate,$obj_acID,$obj_acDate,$obj_exDate,$registrarName,$creditLimit,$creditThreshold,$creditThresholdType,$availableCredit);

if ($op eq 'ack') {
	# acknowledge receipt of a message
	$id = $node->findvalue('@msgID[1]');
	my ($ack_id) = $dbh->selectrow_array("SELECT `id` FROM `poll` WHERE `registrar_id` = '$registrar_id' AND `id` = '$id' LIMIT 1");
	if (!$ack_id) {
		$blob->{resultCode} = 2303; # Object does not exist
	}
	else {
		my $sth = $dbh->prepare("DELETE FROM `poll` WHERE `registrar_id` = ? AND `id` = ?") or die $dbh->errstr;
		$sth->execute($registrar_id,$id) or die $sth->errstr;
		$blob->{resultCode} = 1000;
	}
}
else {
	# $op eq 'req'
	# retrieve the first message from the server message queue
	($id,$qdate,$poll_msg,$poll_msg_type,$obj_name_or_id,$obj_trStatus,$obj_reID,$obj_reDate,$obj_acID,$obj_acDate,$obj_exDate,$registrarName,$creditLimit,$creditThreshold,$creditThresholdType,$availableCredit) = $dbh->selectrow_array("SELECT `id`,`qdate`,`msg`,`msg_type`,`obj_name_or_id`,`obj_trStatus`,`obj_reID`,`obj_reDate`,`obj_acID`,`obj_acDate`,`obj_exDate`,`registrarName`,`creditLimit`,`creditThreshold`,`creditThresholdType`,`availableCredit` FROM `poll` WHERE `registrar_id` = '$registrar_id' ORDER BY `id` ASC LIMIT 1");
	if ($id) {
		$blob->{resultCode} = 1301;
	}
	else {
		$blob->{resultCode} = 1300;
	}
}


# a counter that indicates the number of messages in the queue
my ($counter) = $dbh->selectrow_array("SELECT COUNT(`id`) AS `counter` FROM `poll` WHERE `registrar_id` = '$registrar_id'");

$blob->{command} = 'poll';

$blob->{count} = $counter;
$blob->{id} = $id;
$blob->{msg} = $poll_msg;
$blob->{lang} = 'en-US';
$qdate =~ s/\s/T/g;
$qdate .= '.0Z';
$blob->{qDate} = $qdate;
$blob->{poll_msg_type} = $poll_msg_type;
if ($poll_msg_type eq 'lowBalance') {
	$blob->{registrarName} = $registrarName;
	$blob->{creditLimit} = $creditLimit;
	$blob->{creditThreshold} = $creditThreshold;
	$blob->{creditThresholdType} = $creditThresholdType;
	$blob->{availableCredit} = $availableCredit;
}
elsif ($poll_msg_type eq 'domainTransfer') {
	$blob->{name} = $obj_name_or_id;
	$blob->{obj_trStatus} = $obj_trStatus;
	$blob->{obj_reID} = $obj_reID;
	$obj_reDate =~ s/\s/T/g;
	$obj_reDate .= '.0Z';
	$blob->{obj_reDate} = $obj_reDate;
	$blob->{obj_acID} = $obj_acID;
	$obj_acDate =~ s/\s/T/g;
	$obj_acDate .= '.0Z';
	$blob->{obj_acDate} = $obj_acDate;
	if ($obj_exDate) {
		$obj_exDate =~ s/\s/T/g;
		$obj_exDate .= '.0Z';
		$blob->{obj_exDate} = $obj_exDate;
	}
	$blob->{obj_type} = 'domain';
	$blob->{obj_id} = $obj_name_or_id;
}
elsif ($poll_msg_type eq 'contactTransfer') {
	$blob->{identifier} = $obj_name_or_id;
	$blob->{obj_trStatus} = $obj_trStatus;
	$blob->{obj_reID} = $obj_reID;
	$obj_reDate =~ s/\s/T/g;
	$obj_reDate .= '.0Z';
	$blob->{obj_reDate} = $obj_reDate;
	$blob->{obj_acID} = $obj_acID;
	$obj_acDate =~ s/\s/T/g;
	$obj_acDate .= '.0Z';
	$blob->{obj_acDate} = $obj_acDate;
	$blob->{obj_type} = 'contact';
	$blob->{obj_id} = $obj_name_or_id;
}
my $msg = epp_writer($blob);
print $msg;
my $uptr = update_transaction($msg);

sub update_transaction {
	my $svframe = shift;
	my $sth = $dbh->prepare("UPDATE `registryTransaction`.`transaction_identifier` SET `cmd` = ?, `obj_type` = ?, `obj_id` = ?, `code` = ?, `msg` = ?, `svTRID` = ?, `svTRIDframe` = ?, `svdate` = ?, `svmicrosecond` = ? WHERE `id` = ?") or die $dbh->errstr;
	my $date_for_sv_transaction = microsecond();
	my ($svdate,$svmicrosecond) = split(/\./, $date_for_sv_transaction);
	$sth->execute($blob->{cmd},$blob->{obj_type},$blob->{obj_id},$blob->{resultCode},$blob->{human_readable_message},$blob->{svTRID},$svframe,$svdate,$svmicrosecond,$transaction_id) or die $sth->errstr;
	return 1;
}