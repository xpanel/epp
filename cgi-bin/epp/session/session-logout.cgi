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

my $cltrid = $q->param('clTRID');
$cltrid = 'not-given' unless (defined($cltrid));
my $remote_user = $ENV{REMOTE_USER};


my $blob = {};
$blob->{clTRID} = $cltrid;
$blob->{resultCode} = 1500;
$blob->{command} = 'logout';

my ($registrar_id) = $dbh->selectrow_array("SELECT `id` FROM `registrar` WHERE `clid` = '$remote_user' LIMIT 1");

my $sth = $dbh->prepare("INSERT INTO `registryTransaction`.`transaction_identifier` (`registrar_id`,`clTRID`,`clTRIDframe`,`cldate`,`clmicrosecond`) VALUES(?,?,?,?,?)") or die $dbh->errstr;
my $date_for_cl_transaction = microsecond();
my ($cldate,$clmicrosecond) = split(/\./, $date_for_cl_transaction);
$sth->execute($registrar_id,$cltrid,$frame,$cldate,$clmicrosecond) or die $sth->errstr;
my $transaction_id = $dbh->last_insert_id(undef, undef, undef, undef);

my $date_for_svtrid = date_for_svtrid();
$blob->{svTRID} = $date_for_svtrid . '-clID:' . $registrar_id . '-epp:logout';

my $msg = epp_writer($blob);
print $msg;
my $uptr = update_transaction($msg);


sub update_transaction {
	my $svframe = shift;
	my $sth = $dbh->prepare("UPDATE `registryTransaction`.`transaction_identifier` SET `cmd` = ?, `obj_type` = ?, `obj_id` = ?, `code` = ?, `msg` = ?, `svTRID` = ?, `svTRIDframe` = ?, `svdate` = ?, `svmicrosecond` = ? WHERE `id` = ?") or die $dbh->errstr;
	my $date_for_sv_transaction = microsecond();
	my ($svdate,$svmicrosecond) = split(/\./, $date_for_sv_transaction);
	$sth->execute($blob->{command},$blob->{obj_type},$blob->{obj_id},$blob->{resultCode},$blob->{human_readable_message},$blob->{svTRID},$svframe,$svdate,$svmicrosecond,$transaction_id) or die $sth->errstr;
	return 1;
}